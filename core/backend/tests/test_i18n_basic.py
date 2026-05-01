"""023 Modul A — i18n basic: t(), detect_lang(), middleware request.state."""

from __future__ import annotations

import pytest

from app.i18n import detect_lang, t


def test_t_returns_english_default():
    assert t("errors.stripe_not_configured") == "Stripe not configured"
    assert t("errors.signature_missing") == "Stripe-Signature header missing"


def test_t_translates_to_tr_and_es():
    assert t("errors.stripe_not_configured", "tr") == "Stripe yapılandırılmadı"
    assert t("errors.stripe_not_configured", "es") == "Stripe no configurado"


def test_t_falls_back_to_english_when_key_missing():
    # Missing key in tr → en used; missing in en → key returned
    assert t("nonexistent.key", "tr") == "nonexistent.key"
    assert t("nonexistent.key") == "nonexistent.key"


def test_t_with_format_args():
    msg = t("errors.provider_connection", provider="anthropic", detail="timeout")
    assert "anthropic" in msg
    assert "timeout" in msg


@pytest.mark.parametrize(
    "header,expected",
    [
        (None, "en"),
        ("", "en"),
        ("tr-TR,tr;q=0.9,en;q=0.8", "tr"),
        ("es-ES", "es"),
        ("en-US,en;q=0.9", "en"),
        ("de-DE,de;q=0.9", "en"),
        ("zh-CN,zh,tr;q=0.5", "tr"),
    ],
)
def test_detect_lang_parses_accept_language(header, expected):
    assert detect_lang(header) == expected


def test_middleware_sets_request_state_lang(client):
    """Accept-Language=tr → backend internally lang='tr'.
    Test endpoint kontrolü: /v1/license/status responses (lang etkisi B'de).
    Burada middleware sadece state'e yazıyor — direct endpoint testi yok."""
    r = client.get("/healthz", headers={"Accept-Language": "tr-TR,tr;q=0.9"})
    assert r.status_code == 200
