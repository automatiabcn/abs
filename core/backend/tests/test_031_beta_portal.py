"""031 Modul A — Beta request endpoint."""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.db.models import BetaRequest, EmailQueue
from app.db.session import get_engine


@pytest.fixture(autouse=True)
def _cleanup_beta_email_queue():
    yield
    with Session(get_engine()) as db:
        for r in db.scalars(select(EmailQueue)).all():
            if r.kind and r.kind.startswith("beta_"):
                db.delete(r)
        db.commit()


def _wipe_beta_rows() -> None:
    with Session(get_engine()) as db:
        for r in db.scalars(select(BetaRequest)).all():
            db.delete(r)
        db.commit()


def test_beta_request_persists_pending(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "beta_auto_approve", False)
    _wipe_beta_rows()
    r = client.post(
        "/v1/beta/request",
        json={
            "email": "alice@example.com",
            "name": "Alice",
            "company": "ACME",
            "use_case": "internal coding agent",
            "lang": "en",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["auto_approved"] is False
    assert body["status"] == "pending"

    with Session(get_engine()) as db:
        rows = list(db.scalars(select(BetaRequest)).all())
    assert len(rows) == 1
    assert rows[0].email == "alice@example.com"
    assert rows[0].status == "pending"


def test_beta_request_dedupes_within_24h(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "beta_auto_approve", False)
    _wipe_beta_rows()
    payload = {"email": "dup@example.com", "lang": "en"}
    r1 = client.post("/v1/beta/request", json=payload)
    assert r1.status_code == 200
    r2 = client.post("/v1/beta/request", json=payload)
    assert r2.status_code == 429


def test_beta_request_honeypot_silently_drops(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "beta_auto_approve", False)
    _wipe_beta_rows()
    r = client.post(
        "/v1/beta/request",
        json={"email": "spam@example.com", "website": "https://spam.example"},
    )
    assert r.status_code == 200
    assert r.json()["queued"] is False
    with Session(get_engine()) as db:
        rows = list(db.scalars(select(BetaRequest)).all())
    assert rows == []


def test_beta_request_auto_approves_when_flag_set(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "beta_auto_approve", True)
    _wipe_beta_rows()
    r = client.post(
        "/v1/beta/request",
        json={"email": "auto@example.com", "lang": "en"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["auto_approved"] is True
    assert body["license_jti"]
    assert body["license_jti"].startswith("") and len(body["license_jti"]) >= 16

    with Session(get_engine()) as db:
        rows = list(db.scalars(select(BetaRequest)).all())
    assert rows[0].status == "approved"
    assert rows[0].license_jti is not None


def test_beta_request_manual_mode_status_pending(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "beta_auto_approve", False)
    _wipe_beta_rows()
    r = client.post(
        "/v1/beta/request",
        json={"email": "manual@example.com", "lang": "tr"},
    )
    assert r.status_code == 200
    with Session(get_engine()) as db:
        rows = list(db.scalars(select(BetaRequest)).all())
    assert rows[0].status == "pending"
    assert rows[0].lang == "tr"
