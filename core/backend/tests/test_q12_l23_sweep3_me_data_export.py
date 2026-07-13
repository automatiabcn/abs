"""Q12 Round 19 / L23 sweep 3 — me_data_export.py audit coverage.

Pre-Round 19: me_data_export.py had 10/10 silent raise sites — second
top offender after me_account.py. GDPR Article 15 (right of access /
data portability) endpoints had log_customer_action covering SUCCESS
audits but every FAILURE path was silent — credential stuffing, replay
of stolen license tokens, cross-license job_id enumeration all
invisible to ops.

Round 19 wires emit_event onto every failure path matching the
sweep-2 pattern (me.data_export.{auth,status,download} action
families with reason taxonomy). The auth helper is threaded with
optional `request` so it can emit too.

Side fix (same Q12-L24 follow-up as sweep 2): pre-fix
`f"License verify failed: {exc}"` leaked PyJWT internals to client;
post-fix uses generic `"license_verify_failed"` and audit log carries
the exception class name internally.

This sweep brings L23 to 3/3 FULL CLEAN.
"""

from __future__ import annotations

import logging

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


def _mint_license_bearer(jti: str = "test-jti-l23s3") -> str:
    from app.licensing import generate_license

    return generate_license(jti, valid_days=30)


# ----------------------------------------------------------------------
# Auth path emissions (mirrors sweep 2 contract for me_account)
# ----------------------------------------------------------------------


class TestQ12L23Sweep3DataExportAuth:
    def test_missing_bearer_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post("/v1/me/data-export")
        assert r.status_code == 401
        events = _audits_for(caplog.records, "me.data_export.auth")
        assert events and events[-1]["reason"] == "missing_bearer"

    def test_invalid_bearer_no_str_exc_leak(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.post(
                "/v1/me/data-export",
                headers={"Authorization": "Bearer not.a.real.license.token"},
            )
        # 400 (license verify) or 401 (no JTI) — both audit-emitting.
        assert r.status_code in (400, 401)
        events = _audits_for(caplog.records, "me.data_export.auth")
        assert events
        # Q12-L24 follow-up: client must NOT see PyJWT internals.
        assert "Signature" not in r.text and "Exception" not in r.text


# ----------------------------------------------------------------------
# Status endpoint emissions (job_not_found, not_owner)
# ----------------------------------------------------------------------


class TestQ12L23Sweep3DataExportStatus:
    def test_job_not_found_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        bearer = _mint_license_bearer()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get(
                "/v1/me/data-export/ghost-job-id-l23s3",
                headers={"Authorization": f"Bearer {bearer}"},
            )
        assert r.status_code == 404
        events = _audits_for(caplog.records, "me.data_export.status")
        assert events and events[-1]["reason"] == "job_not_found"


# ----------------------------------------------------------------------
# Download endpoint emissions (job_not_found, not_ready, expired,
# file_missing, not_owner)
# ----------------------------------------------------------------------


class TestQ12L23Sweep3DataExportDownload:
    def test_download_job_not_found_emits_denied(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        bearer = _mint_license_bearer()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            r = client.get(
                "/v1/me/data-export/ghost-job-id/download",
                headers={"Authorization": f"Bearer {bearer}"},
            )
        assert r.status_code == 404
        events = _audits_for(caplog.records, "me.data_export.download")
        assert events and events[-1]["reason"] == "job_not_found"
