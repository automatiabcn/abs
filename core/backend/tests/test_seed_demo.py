"""033 Modul B — Demo data seed script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sqlmodel import Session, select

from app.config import settings
from app.db.models import (
    BetaRequest,
    ConnectedSecret,
    CustomerAuditEntry,
    License,
    VaultAuditEntry,
    WebhookEvent,
    WizardEvent,
)
from app.db.session import get_engine

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "infra" / "scripts" / "seed_demo_data.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    import os

    env = {**os.environ}
    # Inherit the test database + data dir explicitly so the subprocess can
    # write its state marker without falling back to /app/data (read-only).
    env["ABS_DATA_DIR"] = settings.data_dir
    env["ABS_DATABASE_URL"] = settings.database_url
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO / "core" / "backend"),
        env=env,
    )


def _wipe_state_marker() -> None:
    try:
        Path(settings.data_dir, "demo_seed_state.json").unlink(missing_ok=True)
    except Exception:
        pass


def test_seed_creates_realistic_counts():
    _wipe_state_marker()
    out = _run(["--reset"])
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout or "{}")
    counts = data["counts"]
    assert counts["licenses"] == 5
    assert counts["webhook_events"] == 20
    assert counts["customer_audit"] == 50
    assert counts["beta_requests"] == 8


def test_seed_writes_state_marker():
    _wipe_state_marker()
    out = _run(["--reset"])
    assert out.returncode == 0
    state_path = Path(settings.data_dir, "demo_seed_state.json")
    assert state_path.exists()
    state = json.loads(state_path.read_text())
    assert state["seed_version"] == "v1"


def test_seed_idempotent_skip_without_reset():
    _wipe_state_marker()
    _run(["--reset"])
    out2 = _run([])
    assert out2.returncode == 0
    parsed = json.loads(out2.stdout or "{}")
    assert parsed.get("skipped") is True


def test_seed_inserts_into_all_target_tables():
    _wipe_state_marker()
    _run(["--reset"])
    with Session(get_engine()) as db:
        assert any(
            (lic.customer_id_stripe or "").startswith("demo:")
            for lic in db.scalars(select(License)).all()
        )
        assert any(
            (e.event_id or "").startswith("demo_evt_")
            for e in db.scalars(select(WebhookEvent)).all()
        )
        assert any(
            (a.license_jti or "").startswith("demo_jti_")
            for a in db.scalars(select(CustomerAuditEntry)).all()
        )
        assert any(
            (b.email or "").endswith("@meetingco.test")
            for b in db.scalars(select(BetaRequest)).all()
        )
        assert any(
            (v.target_key or "").startswith("demo:")
            for v in db.scalars(select(VaultAuditEntry)).all()
        )
        assert any(
            (w.session_id or "").startswith("demo_sess_")
            for w in db.scalars(select(WizardEvent)).all()
        )
        assert any(
            (c.key_name or "").startswith("demo_")
            for c in db.scalars(select(ConnectedSecret)).all()
        )


def test_seed_reset_wipes_demo_rows_only():
    _wipe_state_marker()
    _run(["--reset"])
    # Insert a NON-demo License row. Reset must not touch it.
    from datetime import datetime, timezone

    with Session(get_engine()) as db:
        db.add(
            License(
                jti="real_jti_keep",
                customer_email="real@x.com",
                customer_id_stripe="cus_real_001",
                tier="self-host",
                seat_count=1,
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    _wipe_state_marker()
    _run(["--reset"])
    with Session(get_engine()) as db:
        survivor = db.scalars(
            select(License).where(License.jti == "real_jti_keep")
        ).first()
    assert survivor is not None
