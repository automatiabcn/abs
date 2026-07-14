"""sweep 2 — me_account.py audit coverage.

Before this change: me_account.py had 11/11 silent raise sites — top
offender in the the audit. Failure paths on the GDPR
account-deletion endpoints (missing bearer, expired confirm token,
JTI mismatch, license not found, already purged) emitted no
structured audit. log_customer_action covered the SUCCESS audit
already, but failure paths — the ones ops actually need traced for
a credential-stuffing or replay incident — were invisible.

This change wires `emit_event(request, action="me.account.*", outcome=
"denied|error", reason=...)` to every failure path while keeping the
existing log_customer_action success channel intact. Helpers
`_verify_bearer_license` and `_verify_delete_token` were threaded
through with an optional `request` parameter so they can emit too.

Side fix (follow-up): `f"License verify failed: {exc}"`
detail was leaking the full exception string to the client. Replaced
with generic `"license_verify_failed"` and the actual exception
class is in the audit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.observability.audit import LOGGER_NAME


# ----------------------------------------------------------------------
# Helpers — mint a bearer license token + a delete-confirm token.
# ----------------------------------------------------------------------


def _mint_license_bearer(jti: str = "test-jti-l23s2") -> str:
    """Use app.licensing.generate_license to mint a real bearer."""
    from app.licensing import generate_license

    return generate_license(jti, valid_days=30)


def _mint_delete_token(
    jti: str, *, expired: bool = False, scope: str = "account.delete"
) -> str:
    from app.config import settings

    now = datetime.now(timezone.utc)
    iat = now - timedelta(hours=48 if expired else 0)
    exp = (now - timedelta(hours=1)) if expired else (now + timedelta(hours=24))
    payload = {
        "sub": jti,
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
        "scope": scope,
    }
    return pyjwt.encode(payload, settings.delete_confirm_jwt_secret, algorithm="HS256")


def _audits_for(records, action_prefix: str) -> list[dict]:
    out = []
    for rec in records:
        if rec.name != LOGGER_NAME:
            continue
        a = getattr(rec, "audit", {}) or {}
        if a.get("action", "").startswith(action_prefix):
            out.append(a)
    return out


# ----------------------------------------------------------------------
# Bearer-license audit emissions
# ----------------------------------------------------------------------


class TestSweep2MeAccountAuth:
    def test_missing_bearer_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post("/v1/me/account/delete-request")
        assert r.status_code == 401
        events = _audits_for(caplog.records, "me.account.auth")
        assert events, "sweep2: missing bearer must emit me.account.auth audit"
        assert events[-1]["reason"] == "missing_bearer"
        assert events[-1]["outcome"] == "denied"

    def test_invalid_bearer_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/me/account/delete-request",
                headers={"Authorization": "Bearer not.a.real.license.token"},
            )
        # verify_license returns 400 for malformed JWT, 401 for missing JTI;
        # the contract is "audit-event emitted on either path".
        assert r.status_code in (400, 401)
        events = _audits_for(caplog.records, "me.account.auth")
        assert events
        assert events[-1]["outcome"] in ("denied", "error")
        # follow-up: response detail must NOT include the raw
        # exception string. Pre-fix `f"License verify failed: {exc}"`
        # would have included PyJWT internals (Signature/Exception/etc.).
        assert "Signature" not in r.text and "Exception" not in r.text


# ----------------------------------------------------------------------
# Delete-token audit emissions
# ----------------------------------------------------------------------


class TestSweep2DeleteToken:
    def test_expired_delete_token_emits_denied_expired(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        bearer = _mint_license_bearer()
        bad = _mint_delete_token("test-jti-l23s2", expired=True)
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/me/account/delete-confirm",
                json={"token": bad},
                headers={"Authorization": f"Bearer {bearer}"},
            )
        assert r.status_code == 400
        events = _audits_for(caplog.records, "me.account.delete_token")
        assert events
        assert events[-1]["reason"] == "expired"

    def test_wrong_scope_delete_token_emits_denied_wrong_scope(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        bearer = _mint_license_bearer()
        bad = _mint_delete_token("test-jti-l23s2", scope="account.read")
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/me/account/delete-confirm",
                json={"token": bad},
                headers={"Authorization": f"Bearer {bearer}"},
            )
        assert r.status_code == 400
        events = _audits_for(caplog.records, "me.account.delete_token")
        assert events
        assert events[-1]["reason"] == "wrong_scope"

    def test_jti_mismatch_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        bearer = _mint_license_bearer(jti="real-jti")
        wrong = _mint_delete_token("attacker-jti")  # mismatched sub
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/me/account/delete-confirm",
                json={"token": wrong},
                headers={"Authorization": f"Bearer {bearer}"},
            )
        assert r.status_code == 403
        events = _audits_for(caplog.records, "me.account.delete_confirm")
        assert events and events[-1]["reason"] == "token_jti_mismatch"


# ----------------------------------------------------------------------
# License-not-found / already-purged audits
# ----------------------------------------------------------------------


class TestSweep2LicenseLookup:
    def test_license_not_found_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Bearer is valid, jti has no License row in DB → 404 + audit.
        bearer = _mint_license_bearer(jti="ghost-jti-no-row")
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/me/account/delete-cancel",
                headers={"Authorization": f"Bearer {bearer}"},
            )
        assert r.status_code == 404
        events = _audits_for(caplog.records, "me.account.delete_cancel")
        assert events and events[-1]["reason"] == "license_not_found"
