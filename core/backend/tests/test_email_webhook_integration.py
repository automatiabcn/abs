"""019 — Webhook checkout.session.completed → 4 onboarding email scheduled."""

from __future__ import annotations

import json

import stripe
from sqlmodel import Session, select

from app.db.models import EmailQueue
from app.db.session import get_engine


def _make_event(event_id: str, email: str, customer: str = "cus_w_test") -> dict:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_email": email,
                "customer": customer,
                "metadata": {"tier": "self-host", "seat_count": "1"},
            }
        },
    }


def test_checkout_completed_schedules_4_onboarding_emails(client, monkeypatch):
    event = _make_event("evt_w_email_001", "wmail@x.co", "cus_w_email_1")
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = client.post(
        "/webhooks/stripe",
        content=json.dumps({"stub": True}).encode(),
        headers={"stripe-signature": "x"},
    )
    assert r.status_code == 200, r.text
    jti = r.json()["jti"]

    with Session(get_engine()) as s:
        rows = s.scalars(
            select(EmailQueue).where(EmailQueue.license_jti == jti)
        ).all()
        kinds = sorted(r.kind for r in rows)
        assert kinds == ["expiry_warning", "recovery", "walkthrough", "welcome"]


def test_duplicate_webhook_does_not_double_schedule(client, monkeypatch):
    """Aynı event.id ikinci geldiğinde duplicate path → ek satır eklenmemeli."""
    event = _make_event("evt_w_email_dup", "wmail-dup@x.co", "cus_w_email_dup")
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r1 = client.post(
        "/webhooks/stripe",
        content=json.dumps({"stub": True}).encode(),
        headers={"stripe-signature": "x"},
    )
    assert r1.status_code == 200
    jti = r1.json()["jti"]

    r2 = client.post(
        "/webhooks/stripe",
        content=json.dumps({"stub": True}).encode(),
        headers={"stripe-signature": "x"},
    )
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True

    with Session(get_engine()) as s:
        rows = s.scalars(
            select(EmailQueue).where(EmailQueue.license_jti == jti)
        ).all()
        # 4 onboarding email — duplicate path ekstra schedule etmedi
        assert len(rows) == 4
