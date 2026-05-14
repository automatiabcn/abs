"""Sprint 2I UAT-047 — Stripe webhook body > 1 MiB rejected with 413
before any signature work, so the worker cannot be OOM'd by a giant
POST."""

from __future__ import annotations

from app.api.webhooks.stripe import STRIPE_WEBHOOK_MAX_BODY_BYTES


def test_content_length_above_cap_rejected_with_413(client):
    big_len = STRIPE_WEBHOOK_MAX_BODY_BYTES + 1
    r = client.post(
        "/webhooks/stripe",
        headers={
            "Content-Length": str(big_len),
            "Stripe-Signature": "t=1,v1=deadbeef",
            "Content-Type": "application/json",
        },
        content=b"a",  # actual body is small; the header lies on purpose.
    )
    assert r.status_code == 413
    assert r.json()["detail"] == "payload_too_large"


def test_body_above_cap_rejected_after_buffering(client):
    """Defence-in-depth — when Content-Length is missing or chunked, the
    handler still verifies the buffered payload before signature work."""
    payload = b"a" * (STRIPE_WEBHOOK_MAX_BODY_BYTES + 1024)
    r = client.post(
        "/webhooks/stripe",
        headers={
            "Stripe-Signature": "t=1,v1=deadbeef",
            "Content-Type": "application/json",
        },
        content=payload,
    )
    assert r.status_code == 413
