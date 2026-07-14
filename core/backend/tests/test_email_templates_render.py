"""5 yeni email template render + subject parse."""

from __future__ import annotations

from app.email.sender import _render


def test_welcome_template_renders():
    """Default (en) render."""
    subject, html = _render(
        "welcome.html",
        customer_email="user@x.co",
        unsubscribe_url="https://x/unsub?t=abc",
    )
    assert "Automatia ABS" in subject
    assert "Welcome" in html
    assert "user@x.co" in html
    assert "abc" in html


def test_walkthrough_template_renders():
    subject, html = _render(
        "walkthrough.html",
        lang="tr",
        customer_email="user@x.co",
        unsubscribe_url="https://x/unsub?t=def",
    )
    assert "Setup" in subject
    assert "6 Adım" in html


def test_first_success_template_renders():
    subject, html = _render(
        "first_success.html",
        lang="tr",
        customer_email="user@x.co",
        first_tool_name="system_status",
        unsubscribe_url="https://x/unsub?t=ghi",
    )
    assert "MCP tool" in subject or "tool çağrın" in subject
    assert "system_status" in html


def test_expiry_warning_template_renders():
    subject, html = _render(
        "expiry_warning.html",
        lang="tr",
        customer_email="user@x.co",
        license_jti="jti_xyz",
        days_left=4,
        expires_at="2026-05-15",
        portal_url="https://abs.automatiabcn.com/manage",
        unsubscribe_url="https://x/unsub?t=jkl",
    )
    assert "4 gün" in subject
    assert "jti_xyz" in html
    assert "2026-05-15" in html


def test_recovery_template_renders():
    subject, html = _render(
        "recovery.html",
        lang="tr",
        customer_email="user@x.co",
        expires_at="2026-04-20",
        unsubscribe_url="https://x/unsub?t=mno",
    )
    assert "geri dön" in subject.lower()
    assert "COMEBACK20" in html
    assert "2026-04-20" in html
