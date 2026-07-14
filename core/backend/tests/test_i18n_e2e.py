"""i18n end-to-end: 3 langs × 3 endpoints = 9 live HTTP checks.

Endpoints exercised:
  POST /webhooks/stripe         (no signature → 400 with localized "missing")
  POST /v1/checkout/create-session (no Stripe key → 503 with localized "not configured")
  POST /v1/billing/portal       (no Stripe key → 503 with localized "not configured")
"""

from __future__ import annotations

import pytest

from app.config import settings


@pytest.fixture()
def _no_stripe(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "")


def _post_no_sig(client, headers):
    return client.post("/webhooks/stripe", content=b"{}", headers=headers)


def _post_checkout(client, headers, body=None):
    return client.post(
        "/v1/checkout/create-session",
        json=body or {"sku": "self-host", "customer_email": "u@x.co"},
        headers=headers,
    )


def _post_portal(client, headers):
    return client.post(
        "/v1/billing/portal",
        json={"customer_email": "u@x.co"},
        headers=headers,
    )


# ---- Webhook signature missing ----------------------------------------------


def test_webhook_missing_sig_en(client):
    r = _post_no_sig(client, {"Accept-Language": "en"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Stripe-Signature header missing"


def test_webhook_missing_sig_tr(client):
    r = _post_no_sig(client, {"Accept-Language": "tr-TR,tr;q=0.9"})
    assert r.status_code == 400
    assert "eksik" in r.json()["detail"].lower()


def test_webhook_missing_sig_es(client):
    r = _post_no_sig(client, {"Accept-Language": "es-ES,es;q=0.9"})
    assert r.status_code == 400
    assert "falta" in r.json()["detail"].lower()


# ---- Checkout no Stripe key -------------------------------------------------


def test_checkout_no_key_en(client, _no_stripe):
    r = _post_checkout(client, {"Accept-Language": "en"})
    assert r.status_code == 503
    assert r.json()["detail"] == "Stripe not configured"


def test_checkout_no_key_tr(client, _no_stripe):
    r = _post_checkout(client, {"Accept-Language": "tr-TR,tr"})
    assert r.status_code == 503
    assert "yapılandırılmadı" in r.json()["detail"].lower()


def test_checkout_no_key_es(client, _no_stripe):
    r = _post_checkout(client, {"Accept-Language": "es-ES"})
    assert r.status_code == 503
    assert "no configurado" in r.json()["detail"].lower()


# ---- Portal no Stripe key ---------------------------------------------------


def test_portal_no_key_en(client, _no_stripe):
    r = _post_portal(client, {"Accept-Language": "en"})
    assert r.status_code == 503
    assert r.json()["detail"] == "Stripe not configured"


def test_portal_no_key_tr(client, _no_stripe):
    r = _post_portal(client, {"Accept-Language": "tr"})
    assert r.status_code == 503
    assert "yapılandırılmadı" in r.json()["detail"].lower()


def test_portal_no_key_es(client, _no_stripe):
    r = _post_portal(client, {"Accept-Language": "es"})
    assert r.status_code == 503
    assert "no configurado" in r.json()["detail"].lower()
