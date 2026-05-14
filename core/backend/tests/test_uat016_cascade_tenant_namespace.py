"""Sprint 2I UAT-016 — cascade cache + breaker tenant namespacing."""

from __future__ import annotations

import pytest

from app.cascade import orchestrator as orch_mod
from app.cascade.cache import prompt_hash
from app.providers.base import BaseProvider
from app.providers.schemas import ProviderError, ProviderResponse


class _CountingProvider(BaseProvider):
    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    async def call(self, prompt, model=None, **kw):
        self.calls += 1
        return ProviderResponse(
            text=f"out:{prompt}",
            model=model or "m",
            provider=self.name,
            elapsed_ms=1,
        )


@pytest.mark.asyncio
async def test_cross_tenant_cache_miss(monkeypatch):
    """The same prompt under two tenant_ids must hit the provider twice
    — tenant B must NEVER see tenant A's cached response."""
    await orch_mod.default_cache.clear()
    provider = _CountingProvider()
    monkeypatch.setattr(orch_mod, "get_provider", lambda _n: provider)

    prompt = "Müşteri X için ne yapmalıyım"
    r_a = await orch_mod.call_with_cascade(
        prompt, primary="counting", model="m", tenant_id="acme"
    )
    r_b = await orch_mod.call_with_cascade(
        prompt, primary="counting", model="m", tenant_id="beta"
    )

    assert provider.calls == 2
    assert r_a.cached is False
    assert r_b.cached is False


@pytest.mark.asyncio
async def test_same_tenant_cache_hit(monkeypatch):
    """Two calls with the same tenant_id share the cache entry."""
    await orch_mod.default_cache.clear()
    provider = _CountingProvider()
    monkeypatch.setattr(orch_mod, "get_provider", lambda _n: provider)

    prompt = "aynı prompt aynı tenant"
    r1 = await orch_mod.call_with_cascade(
        prompt, primary="counting", model="m", tenant_id="acme"
    )
    r2 = await orch_mod.call_with_cascade(
        prompt, primary="counting", model="m", tenant_id="acme"
    )

    assert provider.calls == 1
    assert r1.cached is False
    assert r2.cached is True


@pytest.mark.asyncio
async def test_breaker_isolation_per_tenant(monkeypatch):
    """Tenant A tripping the provider breaker must not block tenant B."""

    class _Flaky(BaseProvider):
        name = "flaky"

        async def call(self, prompt, model=None, **kw):
            raise ProviderError("nope", provider=self.name, transient=True)

    flaky = _Flaky()
    monkeypatch.setattr(orch_mod, "get_provider", lambda _n: flaky)

    # Trip the breaker for tenant A on provider "flaky".
    for _ in range(6):
        await orch_mod.default_breaker.record_failure(
            orch_mod._breaker_key("acme", "flaky")
        )

    assert (
        await orch_mod.default_breaker.allow(
            orch_mod._breaker_key("acme", "flaky")
        )
        is False
    )
    assert (
        await orch_mod.default_breaker.allow(
            orch_mod._breaker_key("beta", "flaky")
        )
        is True
    )


def test_prompt_hash_tenant_namespace():
    """Same prompt+model + different tenant_id → distinct cache keys."""
    a = prompt_hash("hello", "m1", tenant_id="acme")
    b = prompt_hash("hello", "m1", tenant_id="beta")
    c = prompt_hash("hello", "m1", tenant_id="acme")
    assert a != b
    assert a == c
