"""POST /webhooks/stripe — signature + checkout.session.completed flow."""

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


def test_solo_checkout_mints_a_licence():
    """The SKU the live pricing page actually sells is 'solo'. It must map to a
    signable licence tier — a regression here (passing 'solo' straight to
    generate_license) raises ValidationError, 500s the webhook, and the paying
    customer never gets a key. The other webhook tests miss it because they feed
    'self-host', a value app/api/checkout.py never emits."""
    from app.api.webhooks.stripe import _licence_tier_for_sku

    assert _licence_tier_for_sku("solo") == "self-host"
    assert _licence_tier_for_sku("team") == "team"
    assert _licence_tier_for_sku("") == "self-host"
    assert _licence_tier_for_sku("nonsense") == "self-host"


def test_checkout_completed_with_solo_sku_generates_license(client, monkeypatch):
    """End-to-end with the EXACT metadata app/api/checkout.py stamps: tier='solo'.
    Mutation guard: revert the SKU→tier mapping and this webhook raises on mint,
    the POST returns 500, and this assertion fails."""
    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_email": "solo-buyer@example.com",
                "customer": "cus_solo_1",
                # Exactly what checkout.py:118 puts on the Stripe session.
                "metadata": {"tier": "solo", "seat_count": "1", "sku": "solo"},
            }
        },
    }
    monkeypatch.setattr(
        stripe.Webhook, "construct_event", lambda *a, **k: fake_event
    )

    r = client.post(
        "/webhooks/stripe",
        content=json.dumps({"stub": True}).encode(),
        headers={"stripe-signature": "t=1,v1=whatever"},
    )
    assert r.status_code == 200, r.text
    jti = r.json()["jti"]

    with Session(get_engine()) as s:
        row = s.scalars(select(License).where(License.jti == jti)).one()
        assert row.customer_email == "solo-buyer@example.com"
        # Stored as a signable licence tier, not the raw SKU.
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
