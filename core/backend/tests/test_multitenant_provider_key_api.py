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


def _stub_ping(monkeypatch, *, text: str):
    """Override the cascade so the key 'ping' returns a controlled response,
    capturing the api_key the endpoint forwarded."""
    captured: dict = {}

    async def _fake(
        prompt,
        *,
        primary,
        fallbacks=(),
        use_cache=True,
        tenant_id="_global",
        api_key=None,
        **kw,
    ):
        captured["api_key"] = api_key
        from app.providers.schemas import ProviderResponse

        return ProviderResponse(text=text, provider=primary)

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _fake)
    return captured


def test_test_stored_key_ok_and_persists_validation(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    client.post(
        "/v1/admin/provider-keys",
        headers=h,
        json={"provider": "groq", "value": "gsk_stored", "owner_type": "org"},
    )
    cap = _stub_ping(monkeypatch, text="pong")

    r = client.post(
        "/v1/admin/provider-keys/test",
        headers=h,
        json={"provider": "groq", "owner_type": "org"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert cap["api_key"] == "gsk_stored"  # the stored key was used

    # validation state was persisted onto the row
    lr = client.get("/v1/admin/provider-keys", headers=h)
    row = next(k for k in lr.json()["keys"] if k["provider"] == "groq")
    assert row["last_validated_ok"] is True

    # CLEAN UP — the provider_keys table is shared across the full suite; a
    # leftover groq key makes later cascade/degradation tests see groq as
    # "configured" and fail. Delete what this test stored.
    client.request(
        "DELETE",
        "/v1/admin/provider-keys",
        headers=h,
        json={"provider": "groq", "owner_type": "org"},
    )


def test_test_raw_value_before_save_does_not_persist(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    cap = _stub_ping(monkeypatch, text="pong")
    # use a provider no other test stores, so a pre-save probe leaving nothing
    # behind is verifiable regardless of test order
    r = client.post(
        "/v1/admin/provider-keys/test",
        headers=h,
        json={"provider": "gemini", "owner_type": "org", "value": "probe_key"},
    )
    assert r.status_code == 200 and r.json()["ok"] is True
    assert cap["api_key"] == "probe_key"
    # nothing stored → the probed provider must not appear in the list
    lr = client.get("/v1/admin/provider-keys", headers=h)
    assert not any(k["provider"] == "gemini" for k in lr.json()["keys"])


def test_test_bad_key_returns_ok_false(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    cap = _stub_ping(monkeypatch, text="")  # empty response → not ok
    r = client.post(
        "/v1/admin/provider-keys/test",
        headers=h,
        json={"provider": "groq", "owner_type": "org", "value": "gsk_bad"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert cap["api_key"] == "gsk_bad"


def test_test_no_stored_key_is_404(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post(
        "/v1/admin/provider-keys/test",
        headers=h,
        json={"provider": "cohere", "owner_type": "org"},
    )
    assert r.status_code == 404


def test_test_requires_admin(client):
    assert client.post("/v1/admin/provider-keys/test", json={}).status_code in (
        401,
        403,
    )


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
        tenant_slug="acme",
        owner_type="user",
        owner_id="dev@acme.com",
        provider="groq",
        value="USER_GROQ_KEY",
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
        "hi",
        primary="groq",
        tenant_id="acme",
        user_subject="dev@acme.com",
        use_cache=False,
    )
    assert seen["api_key"] == "USER_GROQ_KEY"

    # without context → no api_key (adapter falls back to global settings)
    seen.clear()
    await orch.call_with_cascade(
        "hi", primary="groq", tenant_id="acme", use_cache=False
    )
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
        "hi",
        primary="groq",
        tenant_id="nokeys",
        user_subject="ghost@x.com",
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
