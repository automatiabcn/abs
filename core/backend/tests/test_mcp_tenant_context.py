"""MT Phase 1 (W3) — MCP delegation carries tenant/user → BYOK applies."""

from __future__ import annotations

import pytest

from app.cascade import orchestrator as orch
from app.mcp.context import set_mcp_caller
from app.multitenant import provider_keys as pk
from app.providers.schemas import ProviderResponse


@pytest.fixture(autouse=True)
def _clear_mcp_ctx():
    set_mcp_caller(None, None)
    yield
    set_mcp_caller(None, None)


def _fake_provider(seen):
    class _P:
        name = "groq"

        async def call(self, prompt, model=None, **kwargs):
            seen["api_key"] = kwargs.get("api_key")
            return ProviderResponse(text="ok", provider="groq")

    return _P()


@pytest.mark.asyncio
async def test_mcp_context_drives_byok(monkeypatch):
    """An MCP call (no explicit context) picks up tenant/user from the MCP
    ContextVar, so the per-owner key is injected."""
    from app.config import settings

    monkeypatch.setattr(settings, "provider_key_encryption_key", "k", raising=False)
    pk.set_provider_key(
        tenant_slug="mcp-acme",
        owner_type="user",
        owner_id="dev@acme.com",
        provider="groq",
        value="MCP_USER_KEY",
    )
    seen: dict = {}
    monkeypatch.setattr(orch, "get_provider", lambda name: _fake_provider(seen))

    # Simulate transport_auth stashing the caller from the bearer token.
    set_mcp_caller("mcp-acme", "dev@acme.com")

    # MCP tool calls call_with_cascade with NO explicit context.
    await orch.call_with_cascade("hi", primary="groq", use_cache=False)
    assert seen["api_key"] == "MCP_USER_KEY"


@pytest.mark.asyncio
async def test_explicit_context_overrides_mcp_ctx(monkeypatch):
    """Panel callers pass explicit context; it must win over any MCP ctx."""
    seen: dict = {}
    monkeypatch.setattr(orch, "get_provider", lambda name: _fake_provider(seen))
    set_mcp_caller("mcp-acme", "dev@acme.com")
    # explicit _global tenant + no user → no owner key injected
    await orch.call_with_cascade(
        "hi", primary="groq", tenant_id="other-tenant", use_cache=False
    )
    # other-tenant has no stored key → no override
    assert seen.get("api_key") is None


@pytest.mark.asyncio
async def test_no_mcp_ctx_is_global(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(orch, "get_provider", lambda name: _fake_provider(seen))
    # ContextVar cleared by fixture → behaves as legacy global path
    await orch.call_with_cascade("hi", primary="groq", use_cache=False)
    assert seen.get("api_key") is None
