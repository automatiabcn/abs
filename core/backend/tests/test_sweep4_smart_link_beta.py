"""sweep 4 — smart_link.py + beta_admin.py audit coverage.

An earlier audit:
    app/api/smart_link.py   — 7 silent raise sites:
        * _check_admin (401 missing bearer / 403 invalid token)
        * github_callback (400 invalid/expired/replayed state)
        * github_refresh (404 no token stored)
        * store_api_key (400 unsupported provider, 400 too short,
                         422 provider validation failed)
    app/api/beta_admin.py   — 7 silent raise sites:
        * _require_admin (401 missing bearer / 403 invalid token)
        * list_queue (400 invalid status filter)
        * approve_request (404 not_found / 409 already_rejected)
        * reject_request (404 not_found / 409 already_approved)

These are *operational* security probes that must NOT be silent:
    - Replayed OAuth state (CSRF probe, leaked-state replay) at the
      smart_link callback. Silent today.
    - Brute-forcing /v1/admin/beta/queue with wrong tokens. Silent
      today (logs only show 403 in access log, no actor context, no
      rate-limit counter).
    - Provider key validator failure on /v1/smart-link/api-key — could
      be benign typo or could be credential-stuffing across providers.
      No emit, no signal.

This change wires emit_event onto every gate/denial path mirroring
sweep-2/3 pattern. Brings L23 total to 4/3 deep (sweep 4 across the
remaining 4 offenders identified by founder verify gap).
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import settings
from app.db.models import BetaRequest
from app.db.session import get_engine
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


def _wipe_beta_rows() -> None:
    with Session(get_engine()) as db:
        for r in db.scalars(select(BetaRequest)).all():
            db.delete(r)
        db.commit()


# ----------------------------------------------------------------------
# smart_link admin gate + OAuth state replay
# ----------------------------------------------------------------------


class TestSweep4SmartLinkGate:
    def test_missing_bearer_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post("/v1/smart-link/github/refresh")
        assert r.status_code == 401
        events = _audits_for(caplog.records, "smart_link.admin.gate")
        assert events and events[-1]["reason"] == "missing_bearer"

    def test_wrong_admin_token_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "admin_token", "right-token-l23s4")
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/smart-link/github/refresh",
                headers={"Authorization": "Bearer wrong-token"},
            )
        assert r.status_code == 403
        events = _audits_for(caplog.records, "smart_link.admin.gate")
        assert events and events[-1]["reason"] == "admin_token_invalid"

    def test_oauth_callback_replayed_state_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Forged state — never issued
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get(
                "/v1/smart-link/github/callback",
                params={"code": "abc", "state": "forged-state-l23s4"},
            )
        assert r.status_code == 400
        events = _audits_for(caplog.records, "smart_link.github.callback")
        assert events and events[-1]["reason"] == "state_invalid_or_expired"
        assert events[-1]["provider"] == "github"


# ----------------------------------------------------------------------
# smart_link api-key store
# ----------------------------------------------------------------------


class TestSweep4SmartLinkApiKey:
    def test_unsupported_provider_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/smart-link/api-key",
                json={"provider": "ghost-provider-x", "api_key": "x" * 16},
            )
        assert r.status_code == 400
        events = _audits_for(caplog.records, "smart_link.api_key.store")
        assert events and events[-1]["reason"] == "unsupported_provider"

    def test_short_api_key_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/smart-link/api-key",
                json={"provider": "openai", "api_key": "abc"},
            )
        assert r.status_code == 400
        events = _audits_for(caplog.records, "smart_link.api_key.store")
        assert events and events[-1]["reason"] == "api_key_too_short"


# ----------------------------------------------------------------------
# beta_admin gate
# ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_beta(monkeypatch):
    monkeypatch.setattr(settings, "beta_admin_token", "beta-tok-l23s4")
    yield


class TestSweep4BetaAdminGate:
    def test_missing_bearer_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get("/v1/admin/beta/queue")
        assert r.status_code == 401
        events = _audits_for(caplog.records, "admin.beta.gate")
        assert events and events[-1]["reason"] == "missing_bearer"

    def test_wrong_token_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get(
                "/v1/admin/beta/queue",
                headers={"Authorization": "Bearer wrong-tok"},
            )
        assert r.status_code == 403
        events = _audits_for(caplog.records, "admin.beta.gate")
        assert events and events[-1]["reason"] == "admin_token_invalid"

    def test_invalid_status_filter_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get(
                "/v1/admin/beta/queue",
                params={"status": "ghost-status"},
                headers={"Authorization": "Bearer beta-tok-l23s4"},
            )
        assert r.status_code == 400
        events = _audits_for(caplog.records, "admin.beta.queue")
        assert events and events[-1]["reason"] == "invalid_status_filter"


# ----------------------------------------------------------------------
# beta_admin approve / reject
# ----------------------------------------------------------------------


class TestSweep4BetaApproveReject:
    def test_approve_not_found_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        _wipe_beta_rows()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/admin/beta/999999/approve",
                headers={"Authorization": "Bearer beta-tok-l23s4"},
            )
        assert r.status_code == 404
        events = _audits_for(caplog.records, "admin.beta.approve")
        assert events and events[-1]["reason"] == "request_not_found"

    def test_reject_not_found_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        _wipe_beta_rows()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/admin/beta/999998/reject",
                json={"reason": "spam"},
                headers={"Authorization": "Bearer beta-tok-l23s4"},
            )
        assert r.status_code == 404
        events = _audits_for(caplog.records, "admin.beta.reject")
        assert events and events[-1]["reason"] == "request_not_found"
