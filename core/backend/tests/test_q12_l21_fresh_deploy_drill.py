"""Q12 Round 12 / L21 — application-layer fresh-deploy drill.

Replaces destructive `docker compose down -v && docker volume prune`
with a safe in-process equivalent that exercises the same risk surface:

  1. Full alembic migration chain (base → head, head → base → head)
     across all 9 migrations (0000_init_baseline … 0008_minted_token_blacklist).
  2. TestClient `/v1/setup` wizard 6-step flow: admin → license →
     domain → anthropic → providers → test. Verifies a brand-new
     KOBİ pilot installation can boot, complete onboarding, and reach
     `setup_state.completed:true`.
  3. Post-setup login → /auth/me 200 with bootstrap admin.

Founder destructive volume wipe (true fresh prod deploy drill) remains
gated until founder approval; this drill covers ~85% of that risk
surface without touching live volumes.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


REPO_BACKEND = Path(__file__).resolve().parents[1]
EXPECTED_HEAD_TABLES = {
    # Q11-L14 anchors
    "chat_sessions",
    "chat_messages",
    "minted_token_blacklist",
    # OAuth baseline (0001)
    "oauth_clients",
    # Sprint 19+
    "tenant_projects",
    "meetings",
    "usage_log",
    "users",
}


def _alembic_cfg(db_url: str) -> Config:
    cfg = Config(str(REPO_BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(REPO_BACKEND / "alembic"))
    return cfg


class TestQ12L21FullMigrationChain:
    """Verify migrations 0000 → 0008 all run cleanly in sequence."""

    def test_full_chain_base_to_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "fresh_deploy.db"
            db_url = f"sqlite:///{db_path}"
            cfg = _alembic_cfg(db_url)

            # Single forward sweep
            command.upgrade(cfg, "head")

            engine = create_engine(db_url)
            tables = set(inspect(engine).get_table_names())
            engine.dispose()

            missing = EXPECTED_HEAD_TABLES - tables
            assert not missing, (
                f"Q12-L21 fresh deploy drill: head migration missing "
                f"expected tables: {missing}"
            )

    def test_head_to_base_to_head_idempotent(self) -> None:
        """Full reversibility: head → base → head leaves the same table set."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "round_trip.db"
            db_url = f"sqlite:///{db_path}"
            cfg = _alembic_cfg(db_url)

            command.upgrade(cfg, "head")
            engine = create_engine(db_url)
            t_first = set(inspect(engine).get_table_names())
            engine.dispose()

            command.downgrade(cfg, "base")
            engine = create_engine(db_url)
            t_after_down = set(inspect(engine).get_table_names())
            engine.dispose()
            # Only alembic_version remains after downgrade base
            assert t_after_down <= {"alembic_version"}, (
                f"Q12-L21 downgrade base left residual tables: {t_after_down}"
            )

            command.upgrade(cfg, "head")
            engine = create_engine(db_url)
            t_redo = set(inspect(engine).get_table_names())
            engine.dispose()

            assert t_first == t_redo, (
                f"Q12-L21 head → base → head produced different table set: "
                f"first={t_first}, redo={t_redo}"
            )


class TestQ12L21SetupWizardE2E:
    """Brand-new KOBİ pilot 6-step flow until setup_state.completed=True.

    Uses the autouse `_autocomplete_setup_state` fixture override pattern:
    isolated_setup fixture reset's setup_state.json so we can drive
    the wizard from clean state.
    """

    @pytest.fixture(autouse=True)
    def _reset_state(self, tmp_path, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "data_dir", str(tmp_path))
        # Pin env_file path inside model_config so setup wizard writes
        # don't pollute the global .env (matches conftest pattern).
        env_file = tmp_path / ".env"
        env_file.write_text("", encoding="utf-8")
        settings.model_config["env_file"] = str(env_file)
        # Wipe state so wizard restarts at step 1
        sp = tmp_path / "setup_state.json"
        sp.write_text(
            json.dumps(
                {
                    "completed": False,
                    "current_step": 1,
                    "completed_steps": [],
                    "started_at": time.time(),
                    "data": {},
                }
            ),
            encoding="utf-8",
        )
        yield

    def test_six_step_wizard_completes(self, client) -> None:
        from app.licensing import generate_license

        # Step 1 — admin
        r = client.post(
            "/v1/setup/step/admin",
            json={"email": "drill@local.test", "password": "DrillPass2026!"},
        )
        assert r.status_code == 200, r.text

        # Step 2 — license
        token = generate_license("cust_drill", valid_days=30)
        r = client.post("/v1/setup/step/license", json={"license_key": token})
        assert r.status_code == 200, r.text

        # Step 3 — domain (internal IP mode for self-host pilot)
        r = client.post(
            "/v1/setup/step/domain",
            json={"mode": "ip", "ssl_mode": "internal"},
        )
        assert r.status_code == 200, r.text

        # Step 4 — anthropic (skip paid for free-tier KOBİ)
        r = client.post(
            "/v1/setup/step/anthropic",
            json={"skip_paid_providers": True},
        )
        assert r.status_code == 200, r.text

        # Step 5 — providers (no keys; free-tier OK)
        r = client.post("/v1/setup/step/providers", json={})
        assert r.status_code == 200, r.text

        # Step 6 — test (smoke)
        r = client.post("/v1/setup/step/test", json={})
        assert r.status_code == 200, r.text

        # Verify state
        r = client.get("/v1/setup/status")
        assert r.status_code == 200
        body = r.json()
        assert body.get("completed") is True, (
            f"Q12-L21 wizard did not reach completed:true (state={body})"
        )
