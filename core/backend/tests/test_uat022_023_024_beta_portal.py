"""Sprint 2I UAT-022/023/024 — beta intake hardening.

UAT-022: auto-approve must NOT echo license_jti in the response.
UAT-023: honeypot log line must contain only an email digest, not PII.
UAT-024: duplicate within 24h returns the same neutral 200 body as the
first call (no 429 oracle for email enumeration).
"""

from __future__ import annotations

import logging

import pytest
from sqlmodel import Session, select

from app.db.models import BetaRequest
from app.db.session import get_engine


@pytest.fixture(autouse=True)
def _wipe_beta_rows():
    with Session(get_engine()) as db:
        for r in db.scalars(select(BetaRequest)).all():
            db.delete(r)
        db.commit()
    yield


def test_auto_approve_response_omits_license_jti(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "beta_auto_approve", True)
    r = client.post(
        "/v1/beta/request",
        json={"email": "no-jti-leak@example.com", "lang": "en"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "license_jti" not in body
    assert body["status"] == "queued"
    assert body["check_email"] is True


def test_duplicate_request_returns_neutral_200(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "beta_auto_approve", False)
    payload = {"email": "enum-target@example.com", "lang": "en"}
    r1 = client.post("/v1/beta/request", json=payload)
    r2 = client.post("/v1/beta/request", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    assert "duplicate_recent_request" not in r2.text


def test_honeypot_log_contains_only_email_hash(
    client, caplog: pytest.LogCaptureFixture, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "beta_auto_approve", False)
    pii = "honeypot-victim@example.com"
    with caplog.at_level(logging.INFO, logger="app.api.beta_portal"):
        r = client.post(
            "/v1/beta/request",
            json={"email": pii, "website": "https://spam.example"},
        )
    assert r.status_code == 200
    flat = "\n".join(rec.getMessage() for rec in caplog.records)
    assert pii not in flat
    assert "email_hash=" in flat
