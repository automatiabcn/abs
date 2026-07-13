# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Regression tests for the 2026-07-13 third-eye audit findings.

Four holes, each of which the suite happily passed over before:

1. Setup wizard step 1 rewrites `admin_credentials.json` and its only
   gate was a JSON flag on disk. Lose the state file, lose the panel.
2. The dev-insecure secret guard fired on `env == "prod"` alone, and
   `env` defaults to "dev" — a public deploy that forgot ABS_ENV=prod
   signed cookies with a secret published in the repo.
3. Three admin bearer endpoints compared tokens with `!=`, leaking the
   secret's prefix through response timing.
4. Minted MCP tokens were signed with the panel's `session_secret`, so
   rotating one surface silently broke the other.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ----------------------------------------------------------------------
# 1 — setup wizard cannot re-create an existing admin
# ----------------------------------------------------------------------


@pytest.fixture
def isolated_setup(monkeypatch, tmp_path: Path):
    from app.config import settings

    data = tmp_path / "data"
    data.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(settings, "data_dir", str(data))
    monkeypatch.setattr(settings, "env", "dev")
    settings.model_config["env_file"] = str(env_file)
    return data


class TestSetupAdminTakeover:
    def test_step_admin_refused_when_credentials_already_exist(
        self, isolated_setup: Path, client: TestClient
    ) -> None:
        """The attack: wipe/lose setup_state.json, keep the admin file.

        Pre-fix the wizard read a fresh state (current_step=1, completed
        =False), accepted the request and overwrote the admin's password
        hash — unauthenticated panel takeover. The credentials file is
        the durable fact, so it now closes the step by itself.
        """
        (isolated_setup / "admin_credentials.json").write_text(
            json.dumps(
                {
                    "email": "owner@customer.com",
                    "password_hash": "$2b$12$notarealhashbutlongenough00000000000000000000000000",
                    "created_at": 1.0,
                }
            ),
            encoding="utf-8",
        )
        # No setup_state.json on disk at all — the pre-fix bypass.
        assert not (isolated_setup / "setup_state.json").exists()

        resp = client.post(
            "/v1/setup/step/admin",
            json={"email": "attacker@evil.com", "password": "hunter2hunter2"},
        )

        assert resp.status_code == 409
        stored = json.loads(
            (isolated_setup / "admin_credentials.json").read_text(encoding="utf-8")
        )
        assert stored["email"] == "owner@customer.com"

    def test_step_admin_still_works_on_a_genuine_first_run(
        self, isolated_setup: Path, client: TestClient
    ) -> None:
        """The guard must not break the flow it exists to protect."""
        resp = client.post(
            "/v1/setup/step/admin",
            json={"email": "owner@customer.com", "password": "hunter2hunter2"},
        )

        assert resp.status_code == 200
        assert (isolated_setup / "admin_credentials.json").is_file()


# ----------------------------------------------------------------------
# 2 — the secret guard does not hinge on ABS_ENV alone
# ----------------------------------------------------------------------


class TestProductionSecretGuard:
    def test_public_domain_with_acme_counts_as_production(self) -> None:
        from app.config import Settings, looks_like_production

        s = Settings(domain="abs.customer.com", ssl_mode="acme", env="dev")
        assert looks_like_production(s) is True

    @pytest.mark.parametrize(
        "domain,ssl_mode",
        [
            ("abs.local", "internal"),  # default self-host
            ("abs.local", "acme"),  # special-use TLD gets no public cert
            ("localhost", "acme"),
            ("abs.customer.com", "internal"),  # behind someone else's TLS
        ],
    )
    def test_dev_and_intranet_shapes_are_not_production(
        self, domain: str, ssl_mode: str
    ) -> None:
        from app.config import Settings, looks_like_production

        s = Settings(domain=domain, ssl_mode=ssl_mode, env="dev")
        assert looks_like_production(s) is False

    def test_boot_refuses_dev_secrets_on_a_public_deploy(self) -> None:
        """env is still "dev" — the deploy signal alone must trip the guard."""
        from app.config import Settings, assert_production_safe

        s = Settings(domain="abs.customer.com", ssl_mode="acme", env="dev")

        with pytest.raises(RuntimeError, match="dev-insecure defaults"):
            assert_production_safe(s)

    def test_real_secrets_boot_fine_on_a_public_deploy(self) -> None:
        from app.config import Settings, _DEV_INSECURE_DEFAULTS, assert_production_safe

        overrides = {name: f"real-{name}-value" for name in _DEV_INSECURE_DEFAULTS}
        s = Settings(
            domain="abs.customer.com", ssl_mode="acme", env="dev", **overrides
        )

        assert_production_safe(s)  # must not raise


# ----------------------------------------------------------------------
# 3 — admin bearer comparison is constant-time
# ----------------------------------------------------------------------


class TestBearerConstantTime:
    def test_token_matches_rejects_prefix_and_empty_expected(self) -> None:
        from app.auth.bearer import token_matches

        assert token_matches("s3cret-admin-token", "s3cret-admin-token") is True
        assert token_matches("s3cret-admin-toke", "s3cret-admin-token") is False
        assert token_matches("", "s3cret-admin-token") is False
        # An unconfigured admin_token must never authorise anyone.
        assert token_matches("", "") is False
        assert token_matches("anything", "") is False
        assert token_matches("anything", None) is False

    def test_admin_endpoints_use_the_constant_time_helper(self) -> None:
        """Guards against a future edit reintroducing a `!=` compare."""
        import inspect

        from app.api import demo_admin, smart_link, vault_admin

        for module in (demo_admin, vault_admin, smart_link):
            src = inspect.getsource(module)
            assert "!= settings.admin_token" not in src, module.__name__
            assert "token_matches" in src, module.__name__


# ----------------------------------------------------------------------
# 4 — MCP tokens have a signing key of their own
# ----------------------------------------------------------------------


class TestMcpTokenSecretSplit:
    def test_defaults_to_session_secret_so_existing_tokens_survive(
        self, monkeypatch
    ) -> None:
        from app.api import mcp_tokens
        from app.config import settings

        monkeypatch.setattr(settings, "mcp_token_secret", "")
        monkeypatch.setattr(settings, "session_secret", "panel-key")

        assert mcp_tokens._signing_key() == b"panel-key"

    def test_dedicated_secret_wins_when_set(self, monkeypatch) -> None:
        from app.api import mcp_tokens
        from app.config import settings

        monkeypatch.setattr(settings, "session_secret", "panel-key")
        monkeypatch.setattr(settings, "mcp_token_secret", "mcp-key")

        assert mcp_tokens._signing_key() == b"mcp-key"

    def test_rotating_the_panel_secret_no_longer_kills_mcp_tokens(
        self, monkeypatch
    ) -> None:
        """The operational point of the split, exercised end to end."""
        from app.api import mcp_tokens
        from app.config import settings

        monkeypatch.setattr(settings, "session_secret", "panel-key-v1")
        monkeypatch.setattr(settings, "mcp_token_secret", "mcp-key")
        token = mcp_tokens._sign(
            {"sub": "svc", "scope": "read", "exp": 9_999_999_999}
        )

        # Panel cookie secret rotates; the delegated token must still verify.
        monkeypatch.setattr(settings, "session_secret", "panel-key-v2")

        payload = mcp_tokens.verify_token(token)
        assert payload["sub"] == "svc"
