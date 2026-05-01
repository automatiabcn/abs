"""023 Modul B — i18n hard-coded string replacement regression.

Status_code'lar değişmemeli, sadece detail mesajı locale-aware çevrildi.
"""

from __future__ import annotations

import json

import stripe


def _post_webhook(client, headers=None):
    return client.post(
        "/webhooks/stripe",
        content=json.dumps({}).encode(),
        headers=headers or {},
    )


def test_webhook_signature_missing_message_localized_tr(client):
    """Accept-Language tr → Türkçe message."""
    r = _post_webhook(client, {"Accept-Language": "tr-TR,tr;q=0.9"})
    assert r.status_code == 400
    assert "eksik" in r.json()["detail"].lower()


def test_webhook_signature_missing_message_default_en(client):
    """No Accept-Language → English default."""
    r = _post_webhook(client, {})
    assert r.status_code == 400
    assert r.json()["detail"] == "Stripe-Signature header missing"


def test_webhook_signature_missing_message_es(client):
    r = _post_webhook(client, {"Accept-Language": "es-ES"})
    assert r.status_code == 400
    assert "falta" in r.json()["detail"].lower()


def test_webhook_invalid_signature_message_en_and_tr(client, monkeypatch):
    def _fake_construct(payload, sig_header, secret):
        raise stripe.error.SignatureVerificationError("bad sig", sig_header)

    monkeypatch.setattr(stripe.Webhook, "construct_event", _fake_construct)

    r_en = client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "x"},
    )
    assert r_en.status_code == 400
    assert r_en.json()["detail"] == "Signature verification failed"

    r_tr = client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "x", "Accept-Language": "tr"},
    )
    assert r_tr.status_code == 400
    assert "doğrulanamadı" in r_tr.json()["detail"].lower()
