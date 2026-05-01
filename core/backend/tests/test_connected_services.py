"""026 Modul F — Connected services dashboard endpoint + HTML."""

from __future__ import annotations

import pytest

from app.config import settings
from app.smart_link.vault_secrets import _CACHE, encrypt_secret


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "test-admin-026")


def test_connected_services_requires_admin(client):
    r = client.get("/v1/smart-link/connected-services")
    assert r.status_code == 401


def test_connected_services_returns_providers_and_connected(client, monkeypatch):
    _CACHE.clear()
    encrypt_secret(key_name="cs_test", provider="openai", value="sk-mock-12345678")
    r = client.get(
        "/v1/smart-link/connected-services",
        headers={"Authorization": "Bearer test-admin-026"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "providers" in body
    assert "connected" in body
    assert "count" in body
    # No plaintext leak
    assert "sk-mock" not in str(body)


def test_connect_html_renders(client):
    r = client.get("/v1/smart-link/connect")
    assert r.status_code == 200
    assert "Connected Services" in r.text
    assert "Bearer token" in r.text


def test_connect_html_uses_safe_dom_methods(client):
    """Status panel must NOT use innerHTML (XSS guard)."""
    r = client.get("/v1/smart-link/connect")
    assert r.status_code == 200
    assert "createElement" in r.text
