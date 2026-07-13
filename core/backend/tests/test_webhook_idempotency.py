"""017 — Webhook idempotency: aynı event_id sadece bir kez işlenir."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import stripe
from sqlmodel import Session, select

from app.api.webhooks.idempotency import (
    DuplicateEventError,
    claim_event,
)
from app.db.models import License, WebhookEvent
from app.db.session import get_engine


def _post(client, headers=None):
    return client.post(
        "/webhooks/stripe",
        content=json.dumps({"stub": True}).encode(),
        headers=headers or {"stripe-signature": "t=1,v1=whatever"},
    )


def _checkout_event(
    event_id: str, email: str = "buyer1@x.co", customer: str = "cus_idem_1"
):
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


def test_duplicate_checkout_session_completed_returns_duplicate(client, monkeypatch):
    """Aynı event.id ile iki kez gelirse ikinci 200 + duplicate=True."""
    event = _checkout_event("evt_idem_001", email="dup@x.co", customer="cus_dup_1")
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r1 = _post(client)
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "ok"
    jti1 = r1.json()["jti"]

    r2 = _post(client)
    assert r2.status_code == 200
    body = r2.json()
    assert body.get("duplicate") is True
    assert body.get("event_id") == "evt_idem_001"
    assert body.get("license_jti") == jti1


def test_duplicate_refund_does_not_overwrite_revoked_at(client, monkeypatch):
    """İkinci charge.refunded event_id aynı ise revoked_at değişmez."""
    now = datetime.now(timezone.utc)
    lic = License(
        jti="jti_idem_refund",
        customer_email="r@x.co",
        customer_id_stripe="cus_idem_refund",
        tier="self-host",
        seat_count=1,
        issued_at=now,
        expires_at=now + timedelta(days=365),
    )
    with Session(get_engine()) as s:
        s.add(lic)
        s.commit()

    event = {
        "id": "evt_refund_dup",
        "type": "charge.refunded",
        "data": {"object": {"customer": "cus_idem_refund", "metadata": {}}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r1 = _post(client)
    assert r1.status_code == 200
    assert r1.json()["revoked_jti"] == "jti_idem_refund"

    with Session(get_engine()) as s:
        revoked_at_first = (
            s.scalars(select(License).where(License.jti == "jti_idem_refund"))
            .one()
            .revoked_at
        )

    r2 = _post(client)
    assert r2.status_code == 200
    body = r2.json()
    assert body.get("duplicate") is True
    assert body.get("license_jti") == "jti_idem_refund"

    with Session(get_engine()) as s:
        revoked_at_second = (
            s.scalars(select(License).where(License.jti == "jti_idem_refund"))
            .one()
            .revoked_at
        )
    assert revoked_at_first == revoked_at_second


def test_two_different_event_ids_both_processed(client, monkeypatch):
    """Farklı event.id'li iki event ikisi de işlenir."""
    e1 = _checkout_event("evt_diff_001", email="a@x.co", customer="cus_diff_a")
    e2 = _checkout_event("evt_diff_002", email="b@x.co", customer="cus_diff_b")

    seq = iter([e1, e2])
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: next(seq))

    r1 = _post(client)
    r2 = _post(client)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["status"] == "ok" and r2.json()["status"] == "ok"
    assert r1.json()["jti"] != r2.json()["jti"]
    assert "duplicate" not in r1.json()
    assert "duplicate" not in r2.json()


def test_webhook_events_table_has_event_type_index():
    """`event_type` üzerinde index tanımlı (recent events query hızlı)."""
    from sqlalchemy import inspect

    insp = inspect(get_engine())
    indexes = insp.get_indexes("webhook_events")
    cols = {tuple(ix["column_names"]) for ix in indexes}
    assert ("event_type",) in cols, f"event_type index missing: {indexes}"


def test_claim_event_race_condition_safe():
    """İki claim_event aynı event_id → ikincisi DuplicateEventError raise."""
    with Session(get_engine()) as s:
        row = claim_event(
            s, event_id="evt_race_001", event_type="checkout.session.completed"
        )
        assert isinstance(row, WebhookEvent)

    with Session(get_engine()) as s:
        with pytest.raises(DuplicateEventError) as exc_info:
            claim_event(
                s, event_id="evt_race_001", event_type="checkout.session.completed"
            )
        assert exc_info.value.event_id == "evt_race_001"
