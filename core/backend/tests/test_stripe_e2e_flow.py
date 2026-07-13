"""024 Modul D — Stripe end-to-end flow: checkout → webhook → license → revoke."""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone

import stripe
from sqlmodel import Session, select

from app.config import settings
from app.db.models import License
from app.db.session import get_engine


def _checkout_event(event_id: str, email: str, customer: str = "cus_e2e_1") -> dict:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_email": email,
                "customer": customer,
                "customer_details": {"locale": "en-US", "email": email},
                "metadata": {"tier": "self-host", "seat_count": "1"},
            }
        },
    }


def test_e2e_checkout_create_session_returns_url(client, monkeypatch):
    """POST /v1/checkout/create-session — Stripe Session.create mocked."""
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_e2e")
    monkeypatch.setattr(
        settings, "abs_price_self_host", "price_e2e_self", raising=False
    )

    fake_session = types.SimpleNamespace(
        url="https://checkout.stripe.com/c/pay/cs_e2e_test",
        id="cs_e2e_test",
    )
    monkeypatch.setattr("stripe.checkout.Session.create", lambda **kw: fake_session)

    r = client.post(
        "/v1/checkout/create-session",
        json={"sku": "self-host", "customer_email": "e2e@x.co"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "checkout.stripe.com" in body["checkout_url"]
    assert body["session_id"] == "cs_e2e_test"


def test_e2e_webhook_creates_license_and_emits_email(client, monkeypatch, caplog):
    event = _checkout_event("evt_e2e_create_1", "e2e-create@x.co", "cus_e2e_create")
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)
    monkeypatch.setattr(settings, "smtp_host", "")  # console fallback

    r = client.post(
        "/webhooks/stripe",
        content=json.dumps({"stub": True}).encode(),
        headers={"stripe-signature": "x"},
    )
    assert r.status_code == 200, r.text
    jti = r.json()["jti"]

    with Session(get_engine()) as s:
        lic = s.scalars(select(License).where(License.jti == jti)).first()
        assert lic is not None
        assert lic.customer_email == "e2e-create@x.co"
        assert lic.preferred_lang == "en"


def test_e2e_refund_revokes_license(client, monkeypatch):
    """Seed license, then send charge.refunded → revoked_at set."""
    now = datetime.now(timezone.utc)
    seed = License(
        jti="jti_e2e_refund",
        customer_email="refund-e2e@x.co",
        customer_id_stripe="cus_e2e_refund",
        tier="self-host",
        seat_count=1,
        issued_at=now,
        expires_at=now + timedelta(days=365),
    )
    with Session(get_engine()) as s:
        s.add(seed)
        s.commit()

    refund_event = {
        "id": "evt_e2e_refund_1",
        "type": "charge.refunded",
        "data": {"object": {"customer": "cus_e2e_refund", "metadata": {}}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: refund_event)

    r = client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "x"},
    )
    assert r.status_code == 200
    assert r.json()["revoked_jti"] == "jti_e2e_refund"

    with Session(get_engine()) as s:
        lic = s.scalars(select(License).where(License.jti == "jti_e2e_refund")).one()
        assert lic.revoked_at is not None
        assert lic.revoked_reason == "stripe_refund"


def test_e2e_license_status_reports_revoked(client, monkeypatch):
    """After revoke, /v1/license/status returns status=revoked when JWT matches DB jti."""
    from app.licensing import generate_license, verify_license

    token = generate_license(
        customer_id="cus_e2e_status", tier="self-host", seat_count=1
    )
    payload = verify_license(token)
    jti = payload["jti"]

    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        s.add(
            License(
                jti=jti,
                customer_email="status-e2e@x.co",
                customer_id_stripe="cus_e2e_status",
                tier="self-host",
                seat_count=1,
                issued_at=now,
                expires_at=now + timedelta(days=365),
                revoked_at=now,
                revoked_reason="stripe_refund",
            )
        )
        s.commit()

    monkeypatch.setattr(settings, "license_key", token)
    r = client.get("/v1/license/status")
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"
    assert r.json()["reason"] == "stripe_refund"
