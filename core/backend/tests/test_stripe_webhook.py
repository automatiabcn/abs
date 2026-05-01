"""POST /webhooks/stripe — imza + checkout.session.completed akışı."""

from __future__ import annotations

import json

import stripe
from sqlmodel import Session, select

from app.db.models import License
from app.db.session import get_engine


def test_webhook_missing_signature_returns_400(client):
    r = client.post("/webhooks/stripe", content=b"{}")
    assert r.status_code == 400
    assert r.json()["detail"] == "Stripe-Signature header missing"


def test_webhook_invalid_signature_returns_400(client):
    r = client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )
    assert r.status_code == 400


def test_checkout_completed_generates_license(client, monkeypatch):
    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_email": "buyer@example.com",
                "customer": "cus_test_123",
                "metadata": {"tier": "self-host", "seat_count": "1"},
            }
        },
    }

    def _fake_construct_event(payload, sig_header, secret):
        return fake_event

    monkeypatch.setattr(stripe.Webhook, "construct_event", _fake_construct_event)

    r = client.post(
        "/webhooks/stripe",
        content=json.dumps({"stub": True}).encode(),
        headers={"stripe-signature": "t=1,v1=whatever"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert "jti" in body

    with Session(get_engine()) as s:
        stmt = select(License).where(License.jti == body["jti"])
        row = s.scalars(stmt).one()
        assert row.customer_email == "buyer@example.com"
        assert row.customer_id_stripe == "cus_test_123"
        assert row.tier == "self-host"
        assert row.seat_count == 1


def test_unknown_event_type_is_ignored(client, monkeypatch):
    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        lambda *a, **k: {"type": "invoice.paid"},
    )
    r = client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=x"},
    )
    assert r.status_code == 200
    assert r.json() == {"status": "ignored", "type": "invoice.paid"}
