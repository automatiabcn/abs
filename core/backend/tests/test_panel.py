"""Panel erişim + widget ID parity."""

from __future__ import annotations

# SERVER panel'inden korunması zorunlu widget ID'leri (feature parity sözleşmesi)
REQUIRED_WIDGET_IDS = [
    "brain-iframe",
    "cs-provider-dots",
    "cs-log",
    "spark-deleg",
    "spark-gpu",
    "spark-cache",
    "judge-summary",
    "judge-body",
    "workflow-card",
    "wf-detail-summary",
    "wf-detail-list",
    "cs-cohere-count",
    "cs-cohere-fill",
    "cohere-alert-banner",
    "feat-grid",
    "feat-trend-list",
    "feat-summary",
    "cs-budget-usd",
    "v8-budget-stat",
    "deleg-budget",
]


def _login(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200


def test_panel_without_auth_redirects_to_login(client):
    # TestClient default follow_redirects=True, disable et
    r = client.get("/panel", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/panel/login"


def test_panel_login_page_is_public(client):
    r = client.get("/panel/login")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "Automatia ABS" in body
    assert 'id="login-form"' in body


def test_panel_after_login_renders_html(client):
    _login(client)
    r = client.get("/panel")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "Automatia ABS" in body


def test_panel_preserves_widget_ids(client):
    """SERVER panel'den taşınan 8 widget'ın ID'leri panelde bulunmalı."""
    _login(client)
    body = client.get("/panel").text
    missing = [wid for wid in REQUIRED_WIDGET_IDS if f'id="{wid}"' not in body]
    assert not missing, f"Eksik widget ID'leri: {missing}"


def test_panel_assets_js_served(client):
    # T-R02 — panel.js is now a 5-line ES module shim that imports
    # ./panel/main.js. The SSE wiring lives in panel/sse.js, not the entry.
    r = client.get("/panel/assets/panel.js")
    assert r.status_code == 200
    assert 'import "./panel/main.js"' in r.text

    sse = client.get("/panel/assets/panel/sse.js")
    assert sse.status_code == 200
    assert "EventSource" in sse.text


def test_panel_assets_css_served(client):
    r = client.get("/panel/assets/panel.css")
    assert r.status_code == 200
    assert "--bg0" in r.text
