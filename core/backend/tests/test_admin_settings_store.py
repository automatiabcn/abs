"""Admin settings store — generic per-tenant section persistence (E2)."""

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


def test_settings_requires_admin(client):
    assert client.get("/v1/admin/settings/webhooks").status_code in (401, 403)
    assert client.put("/v1/admin/settings/webhooks", json={"data": {}}).status_code in (401, 403)


def test_put_get_roundtrip(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    payload = {"data": {"slack": "https://hooks.slack.com/x", "email": "ops@x.com"}}
    r = client.put("/v1/admin/settings/webhooks", headers=h, json=payload)
    assert r.status_code == 200, r.text
    g = client.get("/v1/admin/settings/webhooks", headers=h)
    assert g.status_code == 200
    assert g.json()["data"]["slack"] == "https://hooks.slack.com/x"


def test_put_is_idempotent_update(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    client.put("/v1/admin/settings/alerts", headers=h, json={"data": {"quota_warn": 70}})
    client.put("/v1/admin/settings/alerts", headers=h, json={"data": {"quota_warn": 85}})
    g = client.get("/v1/admin/settings/alerts", headers=h)
    assert g.json()["data"]["quota_warn"] == 85


def test_unknown_section_404(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/v1/admin/settings/wizardry", headers=h).status_code == 404
    assert client.put("/v1/admin/settings/wizardry", headers=h, json={"data": {}}).status_code == 404


def test_empty_section_returns_empty_data(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    g = client.get("/v1/admin/settings/security", headers=h)
    assert g.status_code == 200
    assert g.json()["data"] == {}
