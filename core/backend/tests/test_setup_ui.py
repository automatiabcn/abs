"""012 — Setup UI static dosya servis testleri."""

from __future__ import annotations


def test_setup_index_serves_html(client):
    r = client.get("/setup")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert 'data-step="1"' in body
    # Customer-facing wizard carries only the "ABS" product name — the
    # "Automatia" vendor name must never leak into the shipped install flow.
    assert "<h1>ABS</h1>" in body
    assert "Automatia" not in body
    assert 'data-step-key="admin"' in body
    assert 'data-step-key="test"' in body


def test_setup_assets_served(client):
    r_js = client.get("/setup/assets/setup.js")
    assert r_js.status_code == 200
    assert "javascript" in r_js.headers["content-type"]
    assert "loadState" in r_js.text

    r_css = client.get("/setup/assets/setup.css")
    assert r_css.status_code == 200
    assert "css" in r_css.headers["content-type"]
    assert "--brand-primary" in r_css.text
