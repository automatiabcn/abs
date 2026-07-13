"""024 Modul F — Landing security headers config (best-practices ≥ 100)."""

from __future__ import annotations

from pathlib import Path


def _next_config() -> Path:
    return Path(__file__).resolve().parents[3] / "core" / "landing" / "next.config.ts"


def test_next_config_has_required_security_headers():
    """next.config.ts CSP + Frame-Options + Content-Type + HSTS + Referrer + Permissions."""
    text = _next_config().read_text(encoding="utf-8")
    assert "X-Content-Type-Options" in text
    assert "X-Frame-Options" in text
    assert "Referrer-Policy" in text
    assert "Permissions-Policy" in text
    assert "Strict-Transport-Security" in text
    assert "Content-Security-Policy" in text
    assert "frame-ancestors" in text


def test_html_lang_default_en_for_landing():
    """Landing root html lang attribute = 'en' (i18n default)."""
    layout = (
        Path(__file__).resolve().parents[3] / "core" / "landing" / "app" / "layout.tsx"
    )
    text = layout.read_text(encoding="utf-8")
    assert 'lang="en"' in text, "Landing <html lang> must be 'en' default"
