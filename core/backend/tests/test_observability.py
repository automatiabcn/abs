"""observability gap regression.

Closes pre-fix audit found 138/147 raise sites in
`core/backend/app/api/` had NO paired structured log within 3 lines
before the raise (93.9% silent). No request_id correlation middleware
existed. Ops could not trace a credential-stuffing incident across
nginx → backend → cerbos.

This test pins three contracts:

  1. RequestIDMiddleware mounts and echoes `X-Request-ID` on the
     response (in-bound header preserved if safe; UUID4 hex generated
     when absent or malformed).
  2. `emit_event` writes one record on the `abs.audit` logger with
     {action, outcome, request_id} extras and scrubs sensitive keys.
  3. `/auth/login` failure paths emit a `denied` audit event with the
     `email_hint` masked (first 3 chars + `***`) — never the raw email
     and never the password / hash.

If any of these regress, observability rots silently and incident
response loses the corroborating evidence path.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.observability.audit import (
    LOGGER_NAME,
    SAFE_KEYS,
    _scrub,
    emit_event,
)


# ----------------------------------------------------------------------
# 1) RequestIDMiddleware contract
# ----------------------------------------------------------------------


class TestRequestIDMiddleware:
    def test_request_id_generated_when_absent(self, client: TestClient) -> None:
        r = client.get("/auth/me")
        # 401 expected (no cookie) — but the header MUST still be set
        assert "X-Request-ID" in r.headers, (
            "RequestIDMiddleware did not echo X-Request-ID"
        )
        assert len(r.headers["X-Request-ID"]) == 32, (
            "generated request_id should be uuid4().hex (32 chars)"
        )

    def test_request_id_preserved_when_safe(self, client: TestClient) -> None:
        rid = "abc-123_DEADBEEF"
        r = client.get("/auth/me", headers={"X-Request-ID": rid})
        assert r.headers.get("X-Request-ID") == rid, (
            "safe inbound X-Request-ID should be echoed verbatim"
        )

    def test_request_id_replaced_when_malformed(self, client: TestClient) -> None:
        # Contains a banned char (space) → middleware MUST replace, not propagate.
        r = client.get("/auth/me", headers={"X-Request-ID": "bad value!"})
        echoed = r.headers.get("X-Request-ID", "")
        assert echoed != "bad value!", (
            "malformed X-Request-ID must be replaced (input sanitization)"
        )
        assert len(echoed) == 32, "replacement must be uuid4().hex"

    def test_request_id_replaced_when_too_long(self, client: TestClient) -> None:
        r = client.get("/auth/me", headers={"X-Request-ID": "a" * 129})
        echoed = r.headers.get("X-Request-ID", "")
        assert echoed != "a" * 129, (
            "oversized X-Request-ID must be replaced (>128 chars)"
        )


# ----------------------------------------------------------------------
# 2) emit_event helper contract
# ----------------------------------------------------------------------


class TestEmitEventScrub:
    def test_unknown_keys_dropped(self) -> None:
        out = _scrub(
            {
                "reason": "ok",
                "evil_arbitrary_field": "kept?",
                "password": "secret123",
                "api_key": "sk-abc",
                "Authorization": "Bearer xyz",
            }
        )
        assert out == {"reason": "ok"}, (
            "_scrub must keep allowlisted keys + drop sensitive prefixes"
        )

    def test_safe_keys_set_is_explicit(self) -> None:
        # Adding a new safe key must be deliberate — pin the allowlist.
        required = {
            "reason",
            "tenant_id",
            "user_id",
            "email_hint",
            "provider",
            "status_code",
        }
        missing = required - SAFE_KEYS
        assert not missing, f"SAFE_KEYS missing {missing}"

    def test_outcome_normalized_to_error_when_invalid(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Drive a real request so request.state.request_id is populated.
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get("/auth/me")  # triggers emit_event path inside /me
        # We assert outcome normalization separately via direct call:
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/x",
            "headers": [],
        }
        fake = Request(scope)
        fake.state.request_id = "rid-test"
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            caplog.clear()
            emit_event(fake, action="x.y", outcome="totally-bogus")
        records = [r for r in caplog.records if r.name == LOGGER_NAME]
        assert records, "emit_event produced no abs.audit record"
        last = records[-1]
        audit = getattr(last, "audit", None)
        assert audit is not None, "audit dict missing on log record"
        assert audit["outcome"] == "error", "invalid outcome must normalize to 'error'"
        assert audit["request_id"] == "rid-test"
        assert r.status_code == 401  # /auth/me sanity check unrelated


# ----------------------------------------------------------------------
# 3) /auth/login emits structured denial events with masked email
# ----------------------------------------------------------------------


class TestLoginAuditTrail:
    def test_login_email_no_source_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/auth/login",
                json={
                    "email": "ghostuser_unknown@example.test",
                    "password": "ImpossibleP@ss!",
                },
            )
        assert r.status_code == 401
        denials = [
            getattr(rec, "audit", {})
            for rec in caplog.records
            if rec.name == LOGGER_NAME
            and getattr(rec, "audit", {}).get("action") == "auth.login"
            and getattr(rec, "audit", {}).get("outcome") == "denied"
        ]
        assert denials, "/auth/login bad-email must emit denied audit event"
        last = denials[-1]
        # PII guard: never log full email or password
        assert last.get("email_hint", "").endswith("***"), "email_hint must be masked"
        assert "password" not in last
        assert "request_id" in last and len(last["request_id"]) >= 16, (
            "denial event must carry request_id correlation"
        )

    def test_login_no_secret_field_in_audit_record(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            client.post(
                "/auth/login",
                json={"email": "a@b.test", "password": "ZZZ-not-real"},
            )
        for rec in caplog.records:
            if rec.name != LOGGER_NAME:
                continue
            audit = getattr(rec, "audit", {}) or {}
            for forbidden in ("password", "api_key", "secret", "token", "cookie"):
                assert forbidden not in audit, (
                    f"audit record leaked forbidden key '{forbidden}'"
                )
