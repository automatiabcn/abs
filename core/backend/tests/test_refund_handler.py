"""011 — Refund / subscription.deleted webhook handler testleri."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import stripe
from sqlmodel import Session, select

from app.db.models import License
from app.db.session import get_engine


def _seed_license(
    jti: str, customer_id_stripe: str, customer_email: str = "buyer@x.co"
) -> License:
    now = datetime.now(timezone.utc)
    row = License(
        jti=jti,
        customer_email=customer_email,
        customer_id_stripe=customer_id_stripe,
        tier="self-host",
        seat_count=1,
        issued_at=now,
        expires_at=now + timedelta(days=365),
    )
    with Session(get_engine()) as s:
        s.add(row)
        s.commit()
        s.refresh(row)
    return row


def _post_event(client, event: dict):
    return client.post(
        "/webhooks/stripe",
        content=json.dumps({"stub": True}).encode(),
        headers={"stripe-signature": "t=1,v1=whatever"},
    )


def test_charge_refunded_revokes_license(client, monkeypatch):
    seeded = _seed_license(jti="jti_refund_1", customer_id_stripe="cus_refund_1")
    event = {
        "type": "charge.refunded",
        "data": {
            "object": {
                "customer": "cus_refund_1",
                "metadata": {},
            }
        },
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = _post_event(client, event)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["type"] == "charge.refunded"
    assert body["revoked_jti"] == seeded.jti

    with Session(get_engine()) as s:
        row = s.scalars(select(License).where(License.jti == seeded.jti)).one()
        assert row.revoked_at is not None
        assert row.revoked_reason == "stripe_refund"


def test_subscription_deleted_revokes_license(client, monkeypatch):
    seeded = _seed_license(jti="jti_subdel_1", customer_id_stripe="cus_subdel_1")
    event = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "customer": "cus_subdel_1",
                "metadata": {},
            }
        },
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = _post_event(client, event)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["revoked_jti"] == seeded.jti

    with Session(get_engine()) as s:
        row = s.scalars(select(License).where(License.jti == seeded.jti)).one()
        assert row.revoked_reason == "stripe_subscription_deleted"


def test_refund_no_matching_license_ok_response(client, monkeypatch):
    event = {
        "type": "charge.refunded",
        "data": {
            "object": {
                "customer": "cus_no_match_xyz",
                "metadata": {},
            }
        },
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = _post_event(client, event)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["type"] == "charge.refunded"
    assert body["license_found"] is False
