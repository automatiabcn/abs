"""MT Phase 1 — provider-key management endpoints + cascade key override."""

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


# ── endpoints ───────────────────────────────────────────────────────────────


def test_provider_key_requires_admin(client):
    assert client.get("/v1/admin/provider-keys").status_code in (401, 403)
    assert client.post("/v1/admin/provider-keys", json={}).status_code in (401, 403)


def test_set_list_delete_provider_key(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}

    # set an org-level groq key
    r = client.post(
        "/v1/admin/provider-keys",
        headers=h,
        json={"provider": "groq", "value": "gsk_owner_key", "owner_type": "org"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "groq"

    # list — present, no plaintext
    lr = client.get("/v1/admin/provider-keys", headers=h)
    assert lr.status_code == 200
    body = lr.json()
    assert any(k["provider"] == "groq" for k in body["keys"])
    assert "gsk_owner_key" not in lr.text

    # delete
    dr = client.request(
        "DELETE",
        "/v1/admin/provider-keys",
        headers=h,
        json={"provider": "groq", "owner_type": "org"},
    )
    assert dr.status_code == 200
    assert dr.json()["deleted"] is True


def test_set_unknown_provider_rejected(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/provider-keys",
        headers={"Authorization": f"Bearer {tok}"},
        json={"provider": "wizardai", "value": "x" * 10, "owner_type": "org"},
    )
    assert r.status_code == 422


def test_project_owner_requires_owner_id(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/provider-keys",
        headers={"Authorization": f"Bearer {tok}"},
        json={"provider": "groq", "value": "x" * 10, "owner_type": "project"},
    )
    assert r.status_code == 422


# ── cascade override (B2) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cascade_injects_owner_key(monkeypatch):
    """A stored per-user key must be passed to the provider as api_key; with no
    tenant context the provider sees no api_key (global settings path)."""
    from app.cascade import orchestrator as orch
    from app.multitenant import provider_keys as pk
    from app.providers.schemas import ProviderResponse

    pk.set_provider_key(
        tenant_slug="acme", owner_type="user", owner_id="dev@acme.com",
        provider="groq", value="USER_GROQ_KEY",
    )

    seen = {}

    class _FakeProvider:
        name = "groq"

        async def call(self, prompt, model=None, **kwargs):
            seen["api_key"] = kwargs.get("api_key")
            return ProviderResponse(text="ok", provider="groq")

    monkeypatch.setattr(orch, "get_provider", lambda name: _FakeProvider())

    # with user context → owner key injected
    await orch.call_with_cascade(
        "hi", primary="groq", tenant_id="acme", user_subject="dev@acme.com",
        use_cache=False,
    )
    assert seen["api_key"] == "USER_GROQ_KEY"

    # without context → no api_key (adapter falls back to global settings)
    seen.clear()
    await orch.call_with_cascade("hi", primary="groq", tenant_id="acme", use_cache=False)
    assert seen.get("api_key") is None


@pytest.mark.asyncio
async def test_cascade_no_db_key_no_injection(monkeypatch):
    """User context but no stored key → no api_key override (global path)."""
    from app.cascade import orchestrator as orch
    from app.providers.schemas import ProviderResponse

    seen = {}

    class _FakeProvider:
        name = "groq"

        async def call(self, prompt, model=None, **kwargs):
            seen["api_key"] = kwargs.get("api_key")
            return ProviderResponse(text="ok", provider="groq")

    monkeypatch.setattr(orch, "get_provider", lambda name: _FakeProvider())
    await orch.call_with_cascade(
        "hi", primary="groq", tenant_id="nokeys", user_subject="ghost@x.com",
        use_cache=False,
    )
    assert seen.get("api_key") is None


def test_groq_adapter_honors_api_key_kwarg():
    """Adapter-level: api_key kwarg overrides settings in the outgoing call."""
    import asyncio

    from app.providers.groq import adapter as ga

    captured = {}

    async def _fake_chat(*, url, api_key, **kw):
        captured["api_key"] = api_key
        from app.providers.schemas import ProviderResponse

        return ProviderResponse(text="x", provider="groq")

    import app.providers.groq.adapter as mod
    orig = mod.openai_compatible_chat
    mod.openai_compatible_chat = _fake_chat
    try:
        asyncio.run(ga.GroqProvider().call("hi", api_key="OVERRIDE"))
    finally:
        mod.openai_compatible_chat = orig
    assert captured["api_key"] == "OVERRIDE"
