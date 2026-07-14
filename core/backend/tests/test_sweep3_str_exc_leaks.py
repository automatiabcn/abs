"""Q12 Round 25 / L24 sweep 3 — remaining str(exc) / f-string leaks
across me_consent, me_audit, secrets/rotate.

Pre-Round 25 audit (grep `f".*: {exc}"` and `str(exc)[:`) found:
  app/api/me_consent.py:38  raise 401 "License verify failed: {exc}"
  app/api/me_audit.py:34    raise 401 "License verify failed: {exc}"
  app/api/secrets.py:45     raise 500 "Vault yazma hatasi: {exc}"

These are the EXACT same Q12-L24 family that R14 (Stripe checkout/
billing), R18 (me_account), and R19 (me_data_export) already
fixed. Coverage gap was simply that the prior sweeps grepped only
me_account.py + me_data_export.py + auth.py — me_consent.py and
me_audit.py have IDENTICAL `_verify_bearer_license` helpers that
duplicate the leak. Same for secrets.py (vault rotation surface
parallel to vault_admin.py rotate-key, which R23 already cleaned).

Round 25 ships:
  * me_consent  — generic "license_verify_failed" + audit emit_event
                  taxonomy (auth.{denied:missing_bearer | denied:
                  license_invalid | error:license_verify_exception |
                  denied:missing_jti}). Threading: handlers now take
                  Request and pass it through.
  * me_audit    — same fix, same taxonomy.
  * secrets.py  — generic "vault_write_failed" + secrets.rotate audit
                  emit_event taxonomy ({denied:vault_not_configured |
                  denied:unknown_key | error:vault_write_failed |
                  success}).

Contract guards: response body must NOT contain `Signature`,
`Exception`, `<sops`, `age:` strings indicative of the leaked
PyJWT/sops/age internals.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.observability.audit import LOGGER_NAME


def _audits_for(records, action_prefix: str) -> list[dict]:
    out = []
    for rec in records:
        if rec.name != LOGGER_NAME:
            continue
        a = getattr(rec, "audit", {}) or {}
        if a.get("action", "").startswith(action_prefix):
            out.append(a)
    return out


def _mint_license_bearer(jti: str = "test-jti-l24s3") -> str:
    from app.licensing import generate_license

    return generate_license(jti, valid_days=30)


# ----------------------------------------------------------------------
# me_consent — license verify leak fix + audit
# ----------------------------------------------------------------------


class TestQ12L24Sweep3MeConsent:
    def test_invalid_bearer_no_pyjwt_leak(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get(
                "/v1/me/consents",
                headers={"Authorization": "Bearer not.a.real.license.token"},
            )
        assert r.status_code in (400, 401)
        # Q12-L24 family — must NOT leak PyJWT internals.
        assert "Signature" not in r.text
        assert "Exception" not in r.text
        # If we reach license_verify_failed it must be the generic string.
        if "license_verify_failed" in r.text:
            assert "exc" not in r.text.lower() or "Exception" not in r.text
        events = _audits_for(caplog.records, "me.consent.auth")
        assert events  # something fired
        # one of the denial reasons must be present
        reasons = {e.get("reason") for e in events}
        assert reasons & {
            "license_invalid",
            "license_verify_exception",
            "missing_jti",
        }

    def test_missing_bearer_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get("/v1/me/consents")
        assert r.status_code == 401
        events = _audits_for(caplog.records, "me.consent.auth")
        assert events and events[-1]["reason"] == "missing_bearer"


# ----------------------------------------------------------------------
# me_audit — license verify leak fix + audit
# ----------------------------------------------------------------------


class TestQ12L24Sweep3MeAudit:
    def test_invalid_bearer_no_pyjwt_leak(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get(
                "/v1/me/audit-log",
                headers={"Authorization": "Bearer not.a.real.license.token"},
            )
        assert r.status_code in (400, 401)
        assert "Signature" not in r.text and "Exception" not in r.text
        events = _audits_for(caplog.records, "me.audit.auth")
        assert events
        reasons = {e.get("reason") for e in events}
        assert reasons & {
            "license_invalid",
            "license_verify_exception",
            "missing_jti",
        }

    def test_missing_bearer_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get("/v1/me/audit-log")
        assert r.status_code == 401
        events = _audits_for(caplog.records, "me.audit.auth")
        assert events and events[-1]["reason"] == "missing_bearer"

    def test_garbled_token_keeps_response_generic(
        self,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Truly malformed token: must NOT leak PyJWT exception text
        ('Not enough segments', 'Invalid header padding', etc.)."""
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get(
                "/v1/me/audit-log",
                headers={"Authorization": "Bearer garbled..xx"},
            )
        assert r.status_code in (400, 401)
        for needle in (
            "ExpiredSignatureError",
            "DecodeError",
            "Not enough segments",
            "Invalid header padding",
            "InvalidSignatureError",
        ):
            assert needle not in r.text, f"PyJWT internals leaked: {needle}"


# ----------------------------------------------------------------------
# secrets/rotate — vault write leak fix + audit
# ----------------------------------------------------------------------


@pytest.fixture()
def _admin_panel_session(client: TestClient):
    """current_admin needs panel session cookie (same pattern as R24)."""
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


class TestQ12L24Sweep3SecretsRotate:
    def test_vault_not_configured_emits_denied(
        self,
        _admin_panel_session: TestClient,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        # In dev/test the vault is typically not bootstrapped; force the
        # not-configured branch by stubbing sops_available -> False.
        from app.vault import runner as vault_runner

        monkeypatch.setattr(vault_runner, "sops_available", lambda: False)
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = _admin_panel_session.post(
                "/v1/secrets/rotate",
                json={"key": "abs_test_key", "new_value": "v"},
            )
        assert r.status_code == 503
        events = _audits_for(caplog.records, "secrets.rotate")
        assert events and events[-1]["reason"] == "vault_not_configured"

    def test_unknown_key_emits_denied(
        self,
        _admin_panel_session: TestClient,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        from app.vault import cache as vault_cache
        from app.vault import runner as vault_runner

        monkeypatch.setattr(vault_runner, "sops_available", lambda: True)
        monkeypatch.setattr(vault_runner, "master_key_exists", lambda: True)
        monkeypatch.setattr(vault_cache, "known_keys", lambda: {"abs_known_key"})
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = _admin_panel_session.post(
                "/v1/secrets/rotate",
                json={"key": "abs_unknown_xyz", "new_value": "v"},
            )
        assert r.status_code == 400
        events = _audits_for(caplog.records, "secrets.rotate")
        assert events and events[-1]["reason"] == "unknown_key"

    def test_vault_write_failure_no_sops_stderr_leak(
        self,
        _admin_panel_session: TestClient,
        caplog: pytest.LogCaptureFixture,
        monkeypatch,
    ) -> None:
        """write_secret raises VaultError with sops stderr text in args.
        Pre-fix, response body included that text. Post-fix it is
        generic 'vault_write_failed' and error_class is in audit only."""
        from app.vault import cache as vault_cache
        from app.vault import runner as vault_runner

        monkeypatch.setattr(vault_runner, "sops_available", lambda: True)
        monkeypatch.setattr(vault_runner, "master_key_exists", lambda: True)
        monkeypatch.setattr(vault_cache, "known_keys", lambda: {"abs_test_key"})

        def _raise(*a, **k):
            raise vault_runner.VaultError(
                "sops: stderr juice — file path /var/lib/sops/keys.yaml"
            )

        monkeypatch.setattr(vault_runner, "write_secret", _raise)

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = _admin_panel_session.post(
                "/v1/secrets/rotate",
                json={"key": "abs_test_key", "new_value": "v"},
            )
        assert r.status_code == 500
        assert r.json()["detail"] == "vault_write_failed"
        # Response body MUST NOT carry the sops stderr text.
        assert "stderr juice" not in r.text
        assert "/var/lib/sops" not in r.text
        events = _audits_for(caplog.records, "secrets.rotate")
        assert events and events[-1]["outcome"] == "error"
        assert events[-1]["reason"] == "vault_write_failed"
        assert events[-1].get("error_class") == "VaultError"
