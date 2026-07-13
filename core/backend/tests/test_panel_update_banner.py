"""014 — Panel update banner UI içerik kontrolleri."""

from __future__ import annotations

from pathlib import Path

PANEL_DIR = Path(__file__).resolve().parents[1] / "app" / "static" / "panel"


def test_panel_html_contains_update_banner():
    html = (PANEL_DIR / "index.html").read_text(encoding="utf-8")
    assert 'id="update-banner"' in html
    assert 'id="update-version"' in html
    assert 'id="update-summary"' in html
    assert "applyUpdate()" in html


def test_panel_js_handles_update_event():
    # T-R02 — panel.js was split into ES modules. The update-available SSE
    # listener now sits in sse.js; the handler in widgets.js; the
    # /v1/update/apply fetch + window-attached handler in ui.js.
    sse = (PANEL_DIR / "assets" / "panel" / "sse.js").read_text(encoding="utf-8")
    widgets = (PANEL_DIR / "assets" / "panel" / "widgets.js").read_text(
        encoding="utf-8"
    )
    ui = (PANEL_DIR / "assets" / "panel" / "ui.js").read_text(encoding="utf-8")
    assert '"update-available"' in sse
    assert "onUpdateAvailable" in widgets
    assert "/v1/update/apply" in ui
    assert "applyUpdate" in ui


def test_panel_css_update_banner_classes():
    css = (PANEL_DIR / "assets" / "panel.css").read_text(encoding="utf-8")
    assert ".update-banner" in css
    assert ".update-critical" in css


def test_stream_event_order_includes_update_available():
    from app.api.stream import _BUILDERS, _EVENT_ORDER

    assert "update-available" in _EVENT_ORDER
    assert "update-available" in _BUILDERS
