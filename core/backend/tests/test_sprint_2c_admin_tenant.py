# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Sprint 2C ITEM-1 - /v1/admin/tenant + /v1/admin/branding guards."""

from __future__ import annotations

import bcrypt
import pytest

from app.config import settings


def _admin_token(client, monkeypatch) -> str:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(b"s3cret", bcrypt.gensalt()).decode("utf-8"),
    )
    r = client.post("/v1/admin/login", json={"password": "s3cret"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(autouse=True)
def _reset_admin_state():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


def test_get_tenant_requires_admin(client):
    r = client.get("/v1/admin/tenant")
    assert r.status_code == 401


def test_patch_tenant_requires_admin(client):
    r = client.patch("/v1/admin/tenant", json={"name": "Acme"})
    assert r.status_code == 401


def test_patch_branding_requires_admin(client):
    r = client.patch("/v1/admin/branding", json={"primary_color": "#112233"})
    assert r.status_code == 401


def test_get_tenant_seeds_default_row(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.get(
        "/v1/admin/tenant", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"]
    assert "branding_message" in body
    assert "logo_url" in body
    assert "primary_color" in body


def test_patch_tenant_persists_name_and_branding(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.patch(
        "/v1/admin/tenant",
        headers=headers,
        json={"name": "Acme Corp", "branding_message": "Welcome to Acme"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Acme Corp"
    assert r.json()["branding_message"] == "Welcome to Acme"

    r2 = client.get("/v1/admin/tenant", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["name"] == "Acme Corp"
    assert r2.json()["branding_message"] == "Welcome to Acme"


def test_patch_tenant_rejects_invalid_slug(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.patch(
        "/v1/admin/tenant",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "Has Spaces"},
    )
    assert r.status_code == 422
    assert "slug" in r.text.lower()


def test_patch_tenant_caps_branding_message_500(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    overlong = "x" * 1000
    r = client.patch(
        "/v1/admin/tenant",
        headers={"Authorization": f"Bearer {token}"},
        json={"branding_message": overlong},
    )
    assert r.status_code == 422


def test_patch_branding_rejects_data_url(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.patch(
        "/v1/admin/branding",
        headers={"Authorization": f"Bearer {token}"},
        json={"logo_url": "data:image/png;base64,iVBORw"},
    )
    assert r.status_code == 422


def test_patch_branding_rejects_http_scheme(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.patch(
        "/v1/admin/branding",
        headers={"Authorization": f"Bearer {token}"},
        json={"logo_url": "http://attacker.example.com/logo.png"},
    )
    assert r.status_code == 422


def test_patch_branding_accepts_whitelisted_https(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.patch(
        "/v1/admin/branding",
        headers={"Authorization": f"Bearer {token}"},
        json={"logo_url": "https://cdn.automatiabcn.com/logo.png"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["logo_url"] == "https://cdn.automatiabcn.com/logo.png"


def test_patch_branding_rejects_invalid_hex_color(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.patch(
        "/v1/admin/branding",
        headers={"Authorization": f"Bearer {token}"},
        json={"primary_color": "blue"},
    )
    assert r.status_code == 422


def test_patch_branding_accepts_valid_hex_color(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.patch(
        "/v1/admin/branding",
        headers={"Authorization": f"Bearer {token}"},
        json={"primary_color": "#6366f1"},
    )
    assert r.status_code == 200
    assert r.json()["primary_color"] == "#6366f1"


def test_slug_available_invalid_format_returns_false(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.get(
        "/v1/admin/tenant/slug-available?slug=Has-Caps",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["available"] is False
    assert r.json()["reason"] == "invalid_format"


def test_slug_available_current_slug_is_available(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/v1/admin/tenant", headers=headers)
    own = me.json()["slug"]
    r = client.get(
        f"/v1/admin/tenant/slug-available?slug={own}", headers=headers
    )
    assert r.status_code == 200
    assert r.json()["available"] is True
