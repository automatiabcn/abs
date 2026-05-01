"""012 — Refund + expiration email template testleri."""

from __future__ import annotations

import logging

import pytest


def test_refund_email_renders():
    from app.email.sender import _render

    subject, html = _render(
        "license_refund.html",
        customer_email="x@y.com",
        license_jti="abc123",
        refund_date="2026-04-25",
    )
    assert "iade" in subject.lower() or "refunded" in subject.lower()
    assert "x@y.com" in html
    assert "abc123" in html
    assert "2026-04-25" in html


def test_expiration_email_renders():
    from app.email.sender import _render

    subject, html = _render(
        "license_expired.html",
        customer_email="user@biz.io",
        license_jti="jti_exp_42",
        expired_at="2026-05-15",
    )
    assert "süresi" in subject.lower() or "expired" in subject.lower()
    assert "user@biz.io" in html
    assert "jti_exp_42" in html
    assert "2026-05-15" in html


def test_refund_email_console_fallback(monkeypatch, caplog):
    from app.config import settings
    from app.email.sender import send_refund_email

    monkeypatch.setattr(settings, "smtp_host", "")
    caplog.set_level(logging.INFO, logger="app.email.sender")

    send_refund_email(
        to="customer@example.com",
        license_jti="jti_test_console",
        refund_date="2026-04-25",
    )
    # exception fırlatmadı + log mesajı atıldı
    msgs = [rec.getMessage() for rec in caplog.records]
    assert any("console-fallback" in m and "refund" in m for m in msgs), msgs


@pytest.mark.parametrize("kind", ["expiration"])
def test_expiration_email_console_fallback(monkeypatch, caplog, kind):
    from app.config import settings
    from app.email.sender import send_expiration_email

    monkeypatch.setattr(settings, "smtp_host", "")
    caplog.set_level(logging.INFO, logger="app.email.sender")

    send_expiration_email(
        to="user@biz.io",
        license_jti="jti_exp_42",
        expired_at="2026-05-15",
    )
    msgs = [rec.getMessage() for rec in caplog.records]
    assert any("console-fallback" in m and kind in m for m in msgs), msgs
