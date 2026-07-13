"""023 Modul C — Email template multi-lang (en/tr/es) + preferred_lang propagation."""

from __future__ import annotations

import json

import stripe
from sqlmodel import Session, select

from app.db.models import License
from app.db.session import get_engine
from app.email.sender import _render


def test_render_lang_en_picks_english_template():
    subject, html = _render(
        "welcome.html",
        lang="en",
        customer_email="u@x.co",
        unsubscribe_url="https://x/u",
    )
    assert "Welcome" in html
    assert "Welcome to Automatia ABS" in subject


def test_render_lang_es_picks_spanish_template():
    subject, html = _render(
        "welcome.html",
        lang="es",
        customer_email="u@x.co",
        unsubscribe_url="https://x/u",
    )
    assert "Bienvenido" in html
    assert "Bienvenido a Automatia ABS" in subject


def test_render_unknown_lang_falls_back_to_english():
    subject, html = _render(
        "welcome.html",
        lang="de",  # not supported
        customer_email="u@x.co",
        unsubscribe_url="https://x/u",
    )
    assert "Welcome" in html


def test_webhook_propagates_stripe_locale_to_preferred_lang(client, monkeypatch):
    """Stripe customer_details.locale='es-ES' → License.preferred_lang='es'."""
    event = {
        "id": "evt_lang_es_001",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_email": "lang-es@x.co",
                "customer": "cus_lang_es",
                "customer_details": {"locale": "es-ES", "email": "lang-es@x.co"},
                "metadata": {"tier": "self-host", "seat_count": "1"},
            }
        },
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = client.post(
        "/webhooks/stripe",
        content=json.dumps({"stub": True}).encode(),
        headers={"stripe-signature": "x"},
    )
    assert r.status_code == 200, r.text
    jti = r.json()["jti"]

    with Session(get_engine()) as s:
        lic = s.scalars(select(License).where(License.jti == jti)).first()
        assert lic.preferred_lang == "es"
