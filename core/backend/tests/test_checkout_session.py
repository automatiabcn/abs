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
            "sku": "team",
            "seats": 5,
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
    # Seats are the quantity. A five-person team billed as quantity 1 is a team
    # of five paying for one.
    assert captured["line_items"] == [{"price": "price_test_team", "quantity": 5}]
    assert captured["metadata"]["seat_count"] == "5"
    assert captured["metadata"]["sku"] == "team"


def test_a_team_cannot_be_bought_for_one_seat(client, configured_settings, monkeypatch):
    """The per-seat price is only cheaper than Solo below three people — which is
    exactly why a "team" of one must not be sellable at it."""
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(url="https://checkout.stripe.com/c/x", id="cs_x")

    import stripe

    monkeypatch.setattr(stripe.checkout.Session, "create", fake_create)

    r = client.post(
        "/v1/checkout/create-session",
        json={"sku": "team", "seats": 1, "customer_email": "sneaky@example.com"},
    )

    assert r.status_code == 200, r.text
    assert captured["line_items"][0]["quantity"] == 3
    assert captured["metadata"]["seat_count"] == "3"
