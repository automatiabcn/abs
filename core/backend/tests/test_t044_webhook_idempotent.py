"""T-044 — Stripe webhook idempotency + signature tests."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from app.billing_v10.webhook_idempotent import (
    InvalidWebhookSignature,
    ReplayedWebhookError,
    WebhookProcessor,
    verify_signature,
)


def test_process_unique_event_succeeds() -> None:
    p = WebhookProcessor()
    event = p.process(
        event_id="evt_1",
        event_type="checkout.session.completed",
        payload={"id": "x"},
    )
    assert event.audit_hash
    assert p.audit_log()[-1]["event_id"] == "evt_1"


def test_replay_within_window_raises() -> None:
    p = WebhookProcessor()
    p.process(event_id="evt_1", event_type="x", payload={})
    with pytest.raises(ReplayedWebhookError):
        p.process(event_id="evt_1", event_type="x", payload={})


def test_replay_after_window_allowed() -> None:
    p = WebhookProcessor(replay_window_seconds=0)
    p.process(event_id="evt_1", event_type="x", payload={})
    time.sleep(0.01)
    p.process(event_id="evt_1", event_type="x", payload={})


def test_audit_chain_links_consecutive_events() -> None:
    p = WebhookProcessor()
    a = p.process(event_id="e1", event_type="x", payload={})
    b = p.process(event_id="e2", event_type="x", payload={})
    assert a.audit_hash != b.audit_hash


def test_signature_round_trip() -> None:
    secret = "whsec_dummy"
    body = b'{"id":"evt_1"}'
    ts = int(time.time())
    sig = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.".encode("ascii") + body,
        hashlib.sha256,
    ).hexdigest()
    verify_signature(
        payload_bytes=body,
        timestamp=ts,
        signature=sig,
        secret=secret,
    )


def test_signature_rejects_mismatch() -> None:
    with pytest.raises(InvalidWebhookSignature):
        verify_signature(
            payload_bytes=b"{}",
            timestamp=int(time.time()),
            signature="00",
            secret="whsec_dummy",
        )


def test_signature_rejects_replay_window() -> None:
    secret = "whsec_dummy"
    body = b"{}"
    old_ts = int(time.time()) - 3600
    sig = hmac.new(
        secret.encode("utf-8"),
        f"{old_ts}.".encode("ascii") + body,
        hashlib.sha256,
    ).hexdigest()
    with pytest.raises(InvalidWebhookSignature):
        verify_signature(
            payload_bytes=body,
            timestamp=old_ts,
            signature=sig,
            secret=secret,
            max_age_seconds=300,
        )


def test_signature_requires_secret() -> None:
    with pytest.raises(InvalidWebhookSignature):
        verify_signature(
            payload_bytes=b"{}",
            timestamp=int(time.time()),
            signature="x",
            secret="",
        )


def test_process_requires_event_id() -> None:
    with pytest.raises(ValueError):
        WebhookProcessor().process(event_id="", event_type="x", payload={})
