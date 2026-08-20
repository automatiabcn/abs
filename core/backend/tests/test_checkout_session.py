"""Stripe Checkout Session endpoint testleri (mock'lu)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def configured_settings(monkeypatch):
    """stripe_secret_key + both subscription price IDs."""
    from app.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy")
    monkeypatch.setattr(settings, "abs_price_solo", "price_test_solo")
    monkeypatch.setattr(settings, "abs_price_team", "price_test_team")
    return settings


def test_create_session_no_stripe_key_503(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "")
    r = client.post(
        "/v1/checkout/create-session",
        json={"sku": "solo", "customer_email": "test@example.com"},
    )
    assert r.status_code == 503
    assert "Stripe" in r.json()["detail"]


def test_create_session_no_price_id_503(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy")
    monkeypatch.setattr(settings, "abs_price_solo", "")
    r = client.post(
        "/v1/checkout/create-session",
        json={"sku": "solo", "customer_email": "test@example.com"},
    )
    assert r.status_code == 503
    assert "Price ID" in r.json()["detail"]


def test_create_session_invalid_sku_422(client, configured_settings):
    r = client.post(
        "/v1/checkout/create-session",
        json={"sku": "foo", "customer_email": "a@b.co"},
    )
    assert r.status_code == 422


def test_create_session_returns_url(client, configured_settings, monkeypatch):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            url="https://checkout.stripe.com/c/pay/cs_test_xyz",
            id="cs_test_xyz",
        )

    import stripe

    monkeypatch.setattr(stripe.checkout.Session, "create", fake_create)

    r = client.post(
        "/v1/checkout/create-session",
        json={
            "sku": "solo",
            "seats": 1,
            "customer_email": "buyer@example.com",
            "success_url": "https://x.example/ok",
            "cancel_url": "https://x.example/cancel",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_xyz"
    assert body["session_id"] == "cs_test_xyz"
    # captured args sanity
    assert captured["customer_email"] == "buyer@example.com"
    assert captured["line_items"] == [{"price": "price_test_solo", "quantity": 1}]
    assert captured["metadata"]["seat_count"] == "1"
    assert captured["metadata"]["sku"] == "solo"


def test_the_retired_team_sku_cannot_be_bought(client, configured_settings, monkeypatch):
    """One plan since 2026-08-03, and "team" has to be gone from the API too.

    This used to assert that a one-seat team was silently promoted to three.
    That rule belonged to a plan that no longer exists; what matters now is
    that a SKU the pricing page does not offer cannot still be purchased by
    anyone who kept the old request shape.
    """
    called = {"n": 0}

    def fake_create(**kwargs):
        called["n"] += 1
        return SimpleNamespace(url="https://checkout.stripe.com/c/x", id="cs_x")

    import stripe

    monkeypatch.setattr(stripe.checkout.Session, "create", fake_create)

    r = client.post(
        "/v1/checkout/create-session",
        json={"sku": "team", "seats": 3, "customer_email": "sneaky@example.com"},
    )

    assert r.status_code == 422, r.text
    assert called["n"] == 0, "a retired SKU reached Stripe"
