"""Security — the Stripe webhook must fail closed when the secret is unset.

Stripe's `construct_event` treats an empty secret as a valid HMAC key, so an
unconfigured `stripe_webhook_secret` makes every forged signature (computed
with an empty key) verify. These tests pin that the handler rejects with 503
BEFORE reaching construct_event when the secret is empty, and only proceeds to
verification when a secret is configured.
"""

from fastapi.testclient import TestClient

import app.api.webhooks.stripe as stripe_mod
from app.config import settings
from app.main import app


def test_webhook_fails_closed_when_secret_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "")

    # If the guard works, construct_event is never reached. Make it explode so
    # the test fails loudly if the forgeable path is ever taken.
    def _must_not_run(*a, **k):
        raise AssertionError("construct_event reached despite empty secret")

    monkeypatch.setattr(stripe_mod.stripe.Webhook, "construct_event", _must_not_run)

    client = TestClient(app)
    r = client.post(
        "/webhooks/stripe",
        content=b'{"id":"evt_forged","type":"checkout.session.completed"}',
        headers={"stripe-signature": "t=1,v1=forged_with_empty_key"},
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "webhook_not_configured"


def test_webhook_proceeds_to_verification_when_secret_set(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_configured")
    event = {
        "id": "evt_ok_1",
        "type": "customer.subscription.updated",
        "data": {"object": {}},
    }
    monkeypatch.setattr(
        stripe_mod.stripe.Webhook, "construct_event", lambda *a, **k: event
    )

    client = TestClient(app)
    r = client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=ok"},
    )
    # Guard must NOT fire when a secret is configured — the handler processes
    # the (mocked) verified event instead of returning the 503.
    assert r.status_code != 503
