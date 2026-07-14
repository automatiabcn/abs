# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""POST /v1/admin/providers/{id} guards."""

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
        lambda pid, val, **_kw: {"vault": False, "env": False},
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
        lambda pid, val, **_kw: {"vault": False, "env": False},
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


def test_save_persists_key_on_transient_test_failure(client, monkeypatch):
    """A *transient* live-test failure (provider reachable but ping
    inconclusive — timeout / 5xx / rate-limit / thin reasoning-model response)
    must NOT discard an otherwise-valid key. Regression: a working Cerebras
    key (HTTP 200 upstream) used to 422 + get reverted. Now it persists with a
    soft warning in `last_test`."""
    from app.api.admin import providers_save

    token = _admin_token(client, monkeypatch)
    _silence_persistence(monkeypatch)

    async def fake(provider_id):
        return {
            "ok": False,
            "model": None,
            "latency_ms": 5,
            "error": "provider_unreachable_transient",
            "transient": True,
        }

    monkeypatch.setattr(providers_save, "_live_test_provider", fake)

    r = client.post(
        "/v1/admin/providers/cerebras",
        headers={"Authorization": f"Bearer {token}"},
        json={"api_key": "csk-valid-but-flaky-ping", "enabled": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_id"] == "cerebras"
    assert body["configured"] is True
    # The soft warning is surfaced, but the key was still saved.
    assert body["last_test"]["ok"] is False
    assert body["last_test"]["transient"] is True


def test_save_cloudflare_persists_account_id(client, monkeypatch):
    """Cloudflare Workers AI needs an account id beside the token. The save
    endpoint must accept `account_id`, apply it to settings, and report the
    provider configured (token + account id)."""
    from app.config import settings

    token = _admin_token(client, monkeypatch)
    _patch_live_test(monkeypatch, ok=True)
    _silence_persistence(monkeypatch)
    monkeypatch.setattr(settings, "cf_account_id", "", raising=False)
    captured = {}
    monkeypatch.setattr(
        "app.api.setup._persist_encrypted_secret",
        lambda attr, val: captured.update({attr: val}) or True,
    )
    monkeypatch.setattr("app.api.setup._persist_env_var", lambda k, v: True)

    r = client.post(
        "/v1/admin/providers/cloudflare",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "api_key": "cf_token_value_xxxx",
            "enabled": True,
            "account_id": "1a2b3c4d5e6f",
        },
    )
    assert r.status_code == 200, r.text
    assert settings.cf_account_id == "1a2b3c4d5e6f"
    assert captured.get("cf_account_id") == "1a2b3c4d5e6f"
