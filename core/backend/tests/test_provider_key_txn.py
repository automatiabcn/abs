"""Provider key vault + .env persistence is atomic.

Before: an .env IOError after a successful vault write left a half-
persisted state — UI returned 200 but the next boot reloaded settings
from .env and the key was gone. Now the endpoint must either persist
both or roll back the vault and return 500."""

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


def _patch_live_ok(monkeypatch):
    from app.api.admin import providers_save

    async def fake(_pid):
        return {"ok": True, "model": "fake", "latency_ms": 1}

    monkeypatch.setattr(providers_save, "_live_test_provider", fake)


def test_env_write_failure_returns_500_and_rolls_back(client, monkeypatch):
    """When _persist_env_var raises, the handler must rollback the
    in-memory setting + emit 500 instead of swallowing the failure."""
    from app.api import setup as setup_mod
    from app.api.admin import providers_save

    _patch_live_ok(monkeypatch)
    # Vault write succeeds…
    monkeypatch.setattr(setup_mod, "_persist_encrypted_secret", lambda *_a, **_kw: True)

    # …but .env write raises IOError.
    def _boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(setup_mod, "_persist_env_var", _boom)

    monkeypatch.setattr(settings, "groq_api_key", "previous-value")

    async def _noop_invalidate(_pid):
        return None

    monkeypatch.setattr(providers_save, "_invalidate_caches", _noop_invalidate)

    token = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/providers/groq",
        json={"api_key": "new-value", "enabled": True},
        headers={"Cookie": f"abs_admin={token}"},
    )
    assert r.status_code == 500, r.text
    body = r.json()
    assert body["detail"]["error"] == "provider_key_persist_failed"
    # In-memory settings rolled back to the previous value.
    assert settings.groq_api_key == "previous-value"


def test_both_writes_succeed_returns_200(client, monkeypatch):
    """Happy path — both writes report True and the endpoint returns 200."""
    from app.api import setup as setup_mod
    from app.api.admin import providers_save

    _patch_live_ok(monkeypatch)
    monkeypatch.setattr(setup_mod, "_persist_encrypted_secret", lambda *_a, **_kw: True)
    monkeypatch.setattr(setup_mod, "_persist_env_var", lambda *_a, **_kw: True)

    async def _noop_invalidate(_pid):
        return None

    monkeypatch.setattr(providers_save, "_invalidate_caches", _noop_invalidate)

    token = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/providers/groq",
        json={"api_key": "fresh-value", "enabled": True},
        headers={"Cookie": f"abs_admin={token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vault_persisted"] is True
    assert body["env_persisted"] is True


def test_vault_write_failure_returns_500(client, monkeypatch):
    """When the FIRST write (vault) fails, no env write is attempted
    and the endpoint surfaces 500."""
    from app.api import setup as setup_mod
    from app.api.admin import providers_save

    _patch_live_ok(monkeypatch)

    def _vault_boom(*_a, **_kw):
        raise RuntimeError("sops segfault")

    monkeypatch.setattr(setup_mod, "_persist_encrypted_secret", _vault_boom)

    env_calls: list = []
    monkeypatch.setattr(
        setup_mod,
        "_persist_env_var",
        lambda *_a, **_kw: env_calls.append(_a) or True,
    )

    async def _noop_invalidate(_pid):
        return None

    monkeypatch.setattr(providers_save, "_invalidate_caches", _noop_invalidate)

    token = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/providers/groq",
        json={"api_key": "another-value", "enabled": True},
        headers={"Cookie": f"abs_admin={token}"},
    )
    assert r.status_code == 500
    # _persist_env_var must not be called when vault raises first.
    assert env_calls == []
