# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Sprint 2C ITEM-2 - POST /v1/admin/providers/{id} guards."""

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


def _patch_live_test(monkeypatch, ok: bool, error=None):
    from app.api.admin import providers_save

    async def fake(provider_id):
        return {
            "ok": ok,
            "model": "fake-model" if ok else None,
            "latency_ms": 1,
            "error": error,
        }

    monkeypatch.setattr(providers_save, "_live_test_provider", fake)


def _silence_persistence(monkeypatch):
    from app.api.admin import providers_save

    monkeypatch.setattr(
        providers_save,
        "_persist_secret",
        lambda pid, val: {"vault": False, "env": False},
    )
    monkeypatch.setattr(
        providers_save,
        "_persist_enabled_flag",
        lambda pid, en: False,
    )

    async def _noop_invalidate(pid):
        return None

    monkeypatch.setattr(providers_save, "_invalidate_caches", _noop_invalidate)


def test_save_requires_admin(client):
    r = client.post("/v1/admin/providers/groq", json={"api_key": "x"})
    assert r.status_code == 401


def test_save_unknown_provider_404(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/providers/notreal",
        headers={"Authorization": f"Bearer {token}"},
        json={"api_key": "gsk_test", "enabled": True},
    )
    assert r.status_code == 404


def test_save_valid_key_returns_full_mask_no_last4(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    _patch_live_test(monkeypatch, ok=True)
    _silence_persistence(monkeypatch)
    secret = "gsk_live_NEVER_LEAK_LAST4_xxxx1234"
    r = client.post(
        "/v1/admin/providers/groq",
        headers={"Authorization": f"Bearer {token}"},
        json={"api_key": secret, "enabled": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_id"] == "groq"
    assert body["enabled"] is True
    assert body["configured"] is True
    assert "1234" not in body["masked_key"]
    assert secret not in r.text
    for chunk in (secret[-4:], secret[-5:], secret[:5]):
        assert chunk not in r.text


def test_save_invalid_key_with_enabled_returns_422(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    _patch_live_test(monkeypatch, ok=False, error="401 unauthorised")
    _silence_persistence(monkeypatch)
    r = client.post(
        "/v1/admin/providers/groq",
        headers={"Authorization": f"Bearer {token}"},
        json={"api_key": "wrong-key", "enabled": True},
    )
    assert r.status_code == 422


def test_save_empty_key_with_enabled_blocks(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    _silence_persistence(monkeypatch)
    r = client.post(
        "/v1/admin/providers/anthropic",
        headers={"Authorization": f"Bearer {token}"},
        json={"api_key": "", "enabled": True},
    )
    assert r.status_code == 422


def test_save_invalid_key_with_disabled_allows_persist(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    _silence_persistence(monkeypatch)
    r = client.post(
        "/v1/admin/providers/groq",
        headers={"Authorization": f"Bearer {token}"},
        json={"api_key": "gsk_placeholder", "enabled": False},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_save_invalidates_cascade_cache(client, monkeypatch):
    token = _admin_token(client, monkeypatch)
    _patch_live_test(monkeypatch, ok=True)
    invalidated: list[str] = []
    from app.api.admin import providers_save

    monkeypatch.setattr(
        providers_save,
        "_persist_secret",
        lambda pid, val: {"vault": False, "env": False},
    )
    monkeypatch.setattr(
        providers_save,
        "_persist_enabled_flag",
        lambda pid, en: False,
    )

    async def fake_invalidate(pid):
        invalidated.append(pid)

    monkeypatch.setattr(providers_save, "_invalidate_caches", fake_invalidate)

    r = client.post(
        "/v1/admin/providers/groq",
        headers={"Authorization": f"Bearer {token}"},
        json={"api_key": "gsk_xxx", "enabled": True},
    )
    assert r.status_code == 200, r.text
    assert invalidated == ["groq"]
