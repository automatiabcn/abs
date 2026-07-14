# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Invite email i18n templates extracted from inline HTML."""

from __future__ import annotations

from pathlib import Path

import pytest


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "app" / "email" / "templates"


def test_three_locales_exist():
    for lang in ("en", "tr", "es"):
        assert (TEMPLATES_DIR / f"invite_{lang}.html").is_file(), (
            f"missing invite_{lang}.html"
        )


@pytest.mark.parametrize(
    "lang,expected_subject_part",
    [
        ("en", "Join"),
        ("tr", "davet"),
        ("es", "invitado"),
    ],
)
def test_render_invite_per_locale(lang: str, expected_subject_part: str):
    from app.email.sender import _render

    subject, html = _render(
        "invite.html",
        lang=lang,
        tenant_name="acme-test",
        role="member",
        role_label="Member",
        magic_url="https://abs.example.com/auth/magic?token=abc",
        invited_by="founder@acme-test.com",
    )
    assert expected_subject_part.lower() in subject.lower()
    assert "acme-test" in html
    assert "founder@acme-test.com" in html
    assert "https://abs.example.com/auth/magic?token=abc" in html


def test_send_invite_email_uses_lang_default_en(monkeypatch):
    captured: dict = {}

    def fake_send(*, to, subject, html, kind):
        captured.update({"to": to, "subject": subject, "html": html, "kind": kind})

    from app.email import sender

    monkeypatch.setattr(sender, "_send_html", fake_send)
    sender.send_invite_email(
        to="user@example.com",
        tenant_name="acme",
        role="member",
        magic_url="https://abs.example.com/auth/magic?token=t",
        invited_by="root",
    )
    assert captured["kind"] == "invite"
    assert "Join" in captured["subject"] or "invited" in captured["subject"].lower()
    assert "Member" in captured["html"]


def test_send_invite_email_lang_tr_role_localised(monkeypatch):
    captured: dict = {}

    def fake_send(*, to, subject, html, kind):
        captured.update({"to": to, "subject": subject, "html": html, "kind": kind})

    from app.email import sender

    monkeypatch.setattr(sender, "_send_html", fake_send)
    sender.send_invite_email(
        to="user@example.com",
        tenant_name="acme",
        role="admin",
        magic_url="https://abs.example.com/auth/magic?token=t",
        invited_by="root",
        lang="tr",
    )
    assert "Admin" in captured["html"]
    assert "davet" in captured["subject"].lower()
