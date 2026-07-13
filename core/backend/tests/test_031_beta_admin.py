"""031 Modul E — Beta admin queue + approve/reject."""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from app.config import settings
from app.db.models import BetaRequest, EmailQueue, License
from app.db.session import get_engine


def _wipe_beta_rows() -> None:
    with Session(get_engine()) as db:
        for r in db.scalars(select(BetaRequest)).all():
            db.delete(r)
        db.commit()


@pytest.fixture(autouse=True)
def _cleanup_beta_email_queue():
    yield
    with Session(get_engine()) as db:
        for r in db.scalars(select(EmailQueue)).all():
            if r.kind and r.kind.startswith("beta_"):
                db.delete(r)
        db.commit()


def _admin_headers() -> dict:
    return {"Authorization": f"Bearer {settings.beta_admin_token}"}


def test_admin_queue_requires_bearer(client):
    r = client.get("/v1/admin/beta/queue")
    assert r.status_code == 401
    r = client.get("/v1/admin/beta/queue", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 403


def test_admin_queue_lists_pending_requests(client, monkeypatch):
    monkeypatch.setattr(settings, "beta_auto_approve", False)
    _wipe_beta_rows()
    client.post(
        "/v1/beta/request",
        json={"email": "q1@example.com", "lang": "en"},
    )
    client.post(
        "/v1/beta/request",
        json={"email": "q2@example.com", "lang": "tr"},
    )
    r = client.get("/v1/admin/beta/queue", headers=_admin_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    emails = {item["email"] for item in body["items"]}
    assert {"q1@example.com", "q2@example.com"} <= emails


def test_admin_approve_issues_license_and_marks_request(client, monkeypatch):
    monkeypatch.setattr(settings, "beta_auto_approve", False)
    _wipe_beta_rows()
    client.post(
        "/v1/beta/request",
        json={"email": "approve@example.com", "lang": "en"},
    )
    with Session(get_engine()) as db:
        req_id = db.scalars(select(BetaRequest)).first().id

    r = client.post(f"/v1/admin/beta/{req_id}/approve", headers=_admin_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    jti = body["license_jti"]
    assert jti

    with Session(get_engine()) as db:
        req = db.scalars(select(BetaRequest).where(BetaRequest.id == req_id)).first()
        lic = db.scalars(select(License).where(License.jti == jti)).first()
    assert req.status == "approved"
    assert req.license_jti == jti
    assert lic is not None
    assert lic.tier == "beta"


def test_admin_reject_marks_request(client, monkeypatch):
    monkeypatch.setattr(settings, "beta_auto_approve", False)
    _wipe_beta_rows()
    client.post(
        "/v1/beta/request",
        json={"email": "reject@example.com", "lang": "en"},
    )
    with Session(get_engine()) as db:
        req_id = db.scalars(select(BetaRequest)).first().id

    r = client.post(
        f"/v1/admin/beta/{req_id}/reject",
        headers=_admin_headers(),
        json={"reason": "spam"},
    )
    assert r.status_code == 200

    with Session(get_engine()) as db:
        req = db.scalars(select(BetaRequest).where(BetaRequest.id == req_id)).first()
    assert req.status == "rejected"
    assert req.rejected_reason == "spam"
