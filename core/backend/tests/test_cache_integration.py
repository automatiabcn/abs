"""015 — Cascade orchestrator × cache integration testleri.

cache_stats hit/miss counter'ı orchestrator hot path'ine bağlı olmalı.
"""

from __future__ import annotations

import asyncio

import pytest

from app.cascade.cache import SemanticCache, prompt_hash
from app.providers.schemas import ProviderResponse


def _resp(text: str, model: str = "m1") -> ProviderResponse:
    return ProviderResponse(text=text, model=model, provider="fake", elapsed_ms=10)


@pytest.mark.asyncio
async def test_cache_miss_first_call():
    cache = SemanticCache()
    val = await cache.get(prompt_hash("foo", "m1"))
    assert val is None
    s = cache.stats()
    assert s["misses"] == 1
    assert s["hits"] == 0


@pytest.mark.asyncio
async def test_cache_hit_second_call_same_prompt():
    cache = SemanticCache()
    key = prompt_hash("foo", "m1")
    # 1) miss + set
    assert await cache.get(key) is None
    await cache.set(key, _resp("hello"))
    # 2) hit
    val = await cache.get(key)
    assert val is not None
    assert val.text == "hello"
    s = cache.stats()
    assert s["hits"] == 1
    assert s["misses"] == 1
    assert s["hit_rate_pct"] == 50.0


@pytest.mark.asyncio
async def test_cache_different_prompts_no_hit():
    cache = SemanticCache()
    await cache.get(prompt_hash("foo", "m1"))
    await cache.get(prompt_hash("bar", "m1"))
    s = cache.stats()
    assert s["misses"] == 2
    assert s["hits"] == 0


@pytest.mark.asyncio
async def test_cache_ttl_expiry():
    cache = SemanticCache(ttl_seconds=0.05)
    key = prompt_hash("foo", "m1")
    await cache.set(key, _resp("v1"))
    val1 = await cache.get(key)
    assert val1 is not None  # hit
    await asyncio.sleep(0.1)
    val2 = await cache.get(key)
    assert val2 is None  # expired → miss
    s = cache.stats()
    assert s["hits"] == 1
    assert s["misses"] == 1


@pytest.mark.asyncio
async def test_cascade_uses_cache_on_repeat_call(monkeypatch):
    """Aynı prompt 2x → 2. çağrı cache hit, breaker.allow çağrılmaz."""
    from app.cascade import cache as cache_mod
    from app.cascade import orchestrator as orch_mod
    from app.cascade.cache import SemanticCache

    fresh_cache = SemanticCache()
    monkeypatch.setattr(orch_mod, "default_cache", fresh_cache)
    monkeypatch.setattr(cache_mod, "default_cache", fresh_cache)

    call_count = {"n": 0}

    class FakeProvider:
        async def call(self, prompt, model=None, **kw):
            call_count["n"] += 1
            return _resp(f"resp-{prompt}", model or "m1")

    monkeypatch.setattr(orch_mod, "get_provider", lambda name: FakeProvider())

    r1 = await orch_mod.call_with_cascade("hi", primary="fake", model="m1")
    r2 = await orch_mod.call_with_cascade("hi", primary="fake", model="m1")
    assert r1.text == "resp-hi"
    assert r2.text == "resp-hi"
    assert call_count["n"] == 1  # 2. çağrı cache'ten geldi
    s = fresh_cache.stats()
    assert s["hits"] >= 1
    assert s["misses"] >= 1
