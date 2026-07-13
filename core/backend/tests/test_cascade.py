"""Cascade orchestrator + breaker + cache testleri."""

from __future__ import annotations

import asyncio

import pytest

from app.cascade.breaker import CircuitBreaker
from app.cascade.cache import SemanticCache, prompt_hash
from app.cascade import orchestrator as orch_mod
from app.providers.base import BaseProvider
from app.providers.schemas import ProviderError, ProviderResponse


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_marker():
    cache: SemanticCache = SemanticCache(max_entries=10, ttl_seconds=60)
    r = ProviderResponse(text="hello", model="m", provider="p", elapsed_ms=10)
    await cache.set("k", r)
    got = await cache.get("k")
    assert got is not None
    assert got.text == "hello"


@pytest.mark.asyncio
async def test_cache_ttl_expiry():
    cache: SemanticCache = SemanticCache(max_entries=10, ttl_seconds=0.01)
    await cache.set(
        "k", ProviderResponse(text="x", provider="p", model="m", elapsed_ms=1)
    )
    await asyncio.sleep(0.02)
    assert await cache.get("k") is None


def test_prompt_hash_deterministic():
    a = prompt_hash("merhaba", "model-x")
    b = prompt_hash("merhaba", "model-x")
    c = prompt_hash("merhaba", "model-y")
    assert a == b
    assert a != c


@pytest.mark.asyncio
async def test_breaker_opens_after_threshold():
    br = CircuitBreaker(
        fail_threshold=3, fail_window_seconds=60, reset_timeout_seconds=60
    )
    assert await br.allow("p1") is True
    for _ in range(3):
        await br.record_failure("p1")
    assert await br.allow("p1") is False
    snap = br.snapshot()
    assert snap["p1"]["state"] == "open"


@pytest.mark.asyncio
async def test_breaker_recovers_on_success():
    br = CircuitBreaker(
        fail_threshold=2, fail_window_seconds=60, reset_timeout_seconds=60
    )
    await br.record_failure("p2")
    await br.record_success("p2")
    snap = br.snapshot()
    assert snap["p2"]["state"] == "closed"
    assert snap["p2"]["fail_count"] == 0


class _OkProvider(BaseProvider):
    name = "fake_ok"

    async def call(self, prompt, model=None, **kw):
        return ProviderResponse(
            text="ok:" + prompt, model=model or "m", provider=self.name, elapsed_ms=5
        )


class _FailProvider(BaseProvider):
    name = "fake_fail"

    async def call(self, prompt, model=None, **kw):
        raise ProviderError("kapalı", provider=self.name, transient=True)


@pytest.mark.asyncio
async def test_cascade_fallback_to_next_provider(monkeypatch):
    # Cache ve breaker temiz başla
    await orch_mod.default_cache.clear()

    fake_reg = {"a": _FailProvider(), "b": _OkProvider()}
    monkeypatch.setattr(orch_mod, "get_provider", lambda n: fake_reg[n])

    resp = await orch_mod.call_with_cascade(
        "merhaba",
        primary="a",
        fallbacks=("b",),
        model="m1",
        use_cache=False,
    )
    assert resp.provider == "fake_ok"
    assert resp.text == "ok:merhaba"


@pytest.mark.asyncio
async def test_cascade_cache_hit_second_call(monkeypatch):
    await orch_mod.default_cache.clear()
    calls = {"n": 0}

    class _Counting(BaseProvider):
        name = "counting"

        async def call(self, prompt, model=None, **kw):
            calls["n"] += 1
            return ProviderResponse(
                text="once", model=model or "m", provider=self.name, elapsed_ms=1
            )

    monkeypatch.setattr(orch_mod, "get_provider", lambda n: _Counting())
    p = "aynı prompt " + str(id(object()))
    r1 = await orch_mod.call_with_cascade(
        p, primary="counting", model="m", use_cache=True
    )
    r2 = await orch_mod.call_with_cascade(
        p, primary="counting", model="m", use_cache=True
    )
    assert calls["n"] == 1
    assert r1.cached is False
    assert r2.cached is True
