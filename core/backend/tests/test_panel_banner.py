"""012 — Panel demo countdown banner UI testleri (file content assertions)."""

from __future__ import annotations

from pathlib import Path

PANEL_DIR = Path(__file__).resolve().parents[1] / "app" / "static" / "panel"


def test_panel_html_contains_demo_banner():
    html = (PANEL_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="demo-banner"' in html
    assert 'id="demo-days"' in html
    assert "abs.automatiabcn.com" in html


def test_panel_js_handles_license_status_event():
    # T-R02 — panel.js was split into ES modules under panel/. The license
    # status event listener now lives in sse.js, the handler in widgets.js,
    # and the inline-onclick handler in ui.js.
    sse = (PANEL_DIR / "assets" / "panel" / "sse.js").read_text(encoding="utf-8")
    widgets = (PANEL_DIR / "assets" / "panel" / "widgets.js").read_text(
        encoding="utf-8"
    )
    ui = (PANEL_DIR / "assets" / "panel" / "ui.js").read_text(encoding="utf-8")
    assert '"license-status"' in sse
    assert "onLicenseStatus" in widgets
    assert "demo_days_remaining" in widgets
    assert "dismissDemoBanner" in ui


def test_panel_css_demo_banner_classes():
    css = (PANEL_DIR / "assets" / "panel.css").read_text(encoding="utf-8")
    assert ".demo-banner" in css
    assert ".demo-warn" in css
    assert ".demo-danger" in css
