"""Q12 Round 20 / L23 sweep 4 — setup.py + admin/auth.py audit coverage.

Pre-Round 20 inventory:
    app/api/setup.py        — 8 silent raise sites (wizard step gate +
                              lang + license + domain + reset)
    app/api/admin/auth.py   — 9 silent raise sites (admin_required IP
                              gate, missing token, JWT decode failures,
                              login disabled / IP / rate-limit /
                              password)

Both modules sit at *boot-onset* — there is no user_id, no tenant_id,
no auth context yet. Operationally that's exactly when an attacker
probes (admin login brute force, IP whitelist scan, wizard reset
attempts, license key brute-force at /v1/setup/step/license). Pre-fix,
each denial returned a status code and exited; ops had no signal but
the access log row.

Round 20 wires `emit_event` onto every gate/denial path:

    setup.step.gate          (409 setup_already_completed |
                              step_not_active)
    setup.step.complete      (success per step)
    setup.step.license       (denied license_invalid)
    setup.step.domain        (denied domain_invalid)
    setup.lang.set           (denied unsupported_language | success)
    setup.reset              (denied non_dev_env | success)
    setup.wizard.completed   (success final)

    admin.auth.gate          (denied ip_not_whitelisted | jwt rejected
                              | missing token | success panel session)
    admin.login              (denied login_disabled | ip_not_whitelisted
                              | rate_limited | failure password_invalid |
                              success)

The ip_not_whitelisted and missing-bearer paths in admin_required were
the classic "401 silently into the void" hot spots — without them ops
literally cannot tell a forgotten cookie from a hostile probe.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.observability.audit import LOGGER_NAME


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _audits_for(records, action_prefix: str) -> list[dict]:
    out = []
    for rec in records:
        if rec.name != LOGGER_NAME:
            continue
        a = getattr(rec, "audit", {}) or {}
        if a.get("action", "").startswith(action_prefix):
            out.append(a)
    return out


@pytest.fixture
def isolated_setup(monkeypatch, tmp_path: Path):
    from app.config import settings

    data = tmp_path / "data"
    data.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(settings, "data_dir", str(data))
    monkeypatch.setattr(settings, "license_key", "")
    monkeypatch.setattr(settings, "env", "dev")
    settings.model_config["env_file"] = str(env_file)
    return {"data": data, "env": env_file}


# ----------------------------------------------------------------------
# setup.py — wizard step gate audit
# ----------------------------------------------------------------------


class TestQ12L23Sweep4SetupGate:
    def test_step_not_active_emits_denied(
        self, isolated_setup, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Try to skip ahead to step 3 (domain) without doing 1 or 2.
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/setup/step/domain",
                json={"mode": "ip", "ssl_mode": "internal"},
            )
        assert r.status_code == 409
        events = _audits_for(caplog.records, "setup.step.gate")
        assert events, "no setup.step.gate audit emitted on out-of-order step"
        assert events[-1]["reason"] == "step_not_active"
        assert events[-1]["resource_type"] == "domain"

    def test_invalid_domain_emits_denied(
        self, isolated_setup, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Walk to step 3
        client.post(
            "/v1/setup/step/admin",
            json={"email": "owner@x.co", "password": "longSecret123"},
        )
        from app.licensing import generate_license

        client.post(
            "/v1/setup/step/license",
            json={"license_key": generate_license("c1", valid_days=30)},
        )
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/setup/step/domain",
                json={"mode": "domain", "domain": "no-tld", "ssl_mode": "internal"},
            )
        assert r.status_code == 400
        events = _audits_for(caplog.records, "setup.step.domain")
        assert events and events[-1]["reason"] == "domain_invalid"

    def test_admin_step_success_emits_success(
        self, isolated_setup, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/setup/step/admin",
                json={"email": "owner@x.co", "password": "longSecret123"},
            )
        assert r.status_code == 200
        events = _audits_for(caplog.records, "setup.step.complete")
        assert events and events[-1]["resource_type"] == "admin"
        # email_hint must be masked to 3 chars
        assert events[-1].get("email_hint") == "own"


# ----------------------------------------------------------------------
# setup.py — language picker audit
# ----------------------------------------------------------------------


class TestQ12L23Sweep4SetupLang:
    def test_unsupported_lang_emits_denied(
        self, isolated_setup, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post("/v1/setup/lang", json={"lang": "xx"})
        assert r.status_code == 400
        events = _audits_for(caplog.records, "setup.lang.set")
        assert events and events[-1]["reason"] == "unsupported_language"

    def test_supported_lang_emits_success(
        self, isolated_setup, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post("/v1/setup/lang", json={"lang": "tr"})
        assert r.status_code == 200
        events = _audits_for(caplog.records, "setup.lang.set")
        assert events and events[-1]["outcome"] == "success"


# ----------------------------------------------------------------------
# setup.py — reset (dev-only) audit
# ----------------------------------------------------------------------


class TestQ12L23Sweep4SetupReset:
    def test_reset_in_prod_emits_denied(
        self,
        isolated_setup,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "env", "prod")
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post("/v1/setup/reset")
        assert r.status_code == 403
        events = _audits_for(caplog.records, "setup.reset")
        assert events and events[-1]["reason"] == "non_dev_env"

    def test_reset_in_dev_emits_success(
        self, isolated_setup, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post("/v1/setup/reset")
        assert r.status_code == 200
        events = _audits_for(caplog.records, "setup.reset")
        assert events and events[-1]["outcome"] == "success"


# ----------------------------------------------------------------------
# admin/auth.py — login denial paths
# ----------------------------------------------------------------------


@pytest.fixture
def _admin_creds(monkeypatch):
    """Mint a known bcrypt admin_password_hash so /v1/admin/login can succeed."""
    import bcrypt

    from app.api.admin import auth as admin_mod
    from app.config import settings

    pwd = "AdminCorrectHorseBatteryStaple"
    hashed = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
    monkeypatch.setattr(settings, "admin_password_hash", hashed)
    monkeypatch.setattr(settings, "admin_jwt_secret", "test-secret-l23s4")
    monkeypatch.setattr(settings, "admin_ip_whitelist", "")
    admin_mod._reset_state_for_tests()
    return {"password": pwd}


class TestQ12L23Sweep4AdminLogin:
    def test_login_disabled_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch
    ) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "admin_password_hash", "")
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post("/v1/admin/login", json={"password": "x"})
        assert r.status_code == 503
        events = _audits_for(caplog.records, "admin.login")
        assert events and events[-1]["reason"] == "login_disabled_no_password_hash"

    def test_password_invalid_emits_failure(
        self, _admin_creds, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post("/v1/admin/login", json={"password": "wrong"})
        assert r.status_code == 401
        events = _audits_for(caplog.records, "admin.login")
        assert events and events[-1]["outcome"] == "failure"
        assert events[-1]["reason"] == "password_invalid"
        # CRITICAL — submitted password must NEVER appear in audit context.
        for ev in events:
            assert "wrong" not in str(ev)

    def test_password_valid_emits_success(
        self, _admin_creds, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/admin/login", json={"password": _admin_creds["password"]}
            )
        assert r.status_code == 200
        events = _audits_for(caplog.records, "admin.login")
        assert events and events[-1]["outcome"] == "success"

    def test_ip_not_whitelisted_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch
    ) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "admin_password_hash", "x")
        monkeypatch.setattr(settings, "admin_ip_whitelist", "10.10.10.10")
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post("/v1/admin/login", json={"password": "x"})
        assert r.status_code == 403
        events = _audits_for(caplog.records, "admin.login")
        assert events and events[-1]["reason"] == "ip_not_whitelisted"


# ----------------------------------------------------------------------
# admin/auth.py — admin_required gate
# ----------------------------------------------------------------------


class TestQ12L23Sweep4AdminGate:
    def test_missing_bearer_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get("/v1/admin/me")
        assert r.status_code == 401
        events = _audits_for(caplog.records, "admin.auth.gate")
        assert events and events[-1]["reason"] == "missing_bearer_and_cookie"

    def test_expired_jwt_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch
    ) -> None:
        import jwt as pyjwt

        from app.config import settings

        monkeypatch.setattr(settings, "admin_jwt_secret", "test-secret-l23s4")
        # Expired one minute ago.
        token = pyjwt.encode(
            {"sub": "admin", "scope": "admin", "exp": 1, "iat": 0},
            "test-secret-l23s4",
            algorithm="HS256",
        )
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get(
                "/v1/admin/me", headers={"Authorization": f"Bearer {token}"}
            )
        assert r.status_code == 401
        events = _audits_for(caplog.records, "admin.auth.gate")
        assert events
        # detail strings vary; just assert we observed a denial reason.
        assert events[-1]["outcome"] == "denied"
        assert events[-1]["status_code"] == 401
