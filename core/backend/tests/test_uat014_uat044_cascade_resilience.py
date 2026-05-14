"""Sprint 2I UAT-014 + UAT-044 — cascade non-ProviderError fallback +
503 + structured detail when every provider is down."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.cascade import orchestrator as orch_mod
from app.providers.base import BaseProvider
from app.providers.schemas import ProviderError, ProviderResponse


class _RaisingProvider(BaseProvider):
    name = "raiser"

    def __init__(self, exc_factory):
        self.exc_factory = exc_factory

    async def call(self, prompt, model=None, **kw):
        raise self.exc_factory()


class _OkProvider(BaseProvider):
    name = "ok"

    async def call(self, prompt, model=None, **kw):
        return ProviderResponse(
            text="ok", model=model or "m", provider=self.name, elapsed_ms=1
        )


@pytest.mark.asyncio
async def test_connection_error_falls_through_to_next_provider(monkeypatch):
    """UAT-014 — ConnectionError used to bypass cascade and raise 500."""
    await orch_mod.default_cache.clear()
    chain = {
        "a": _RaisingProvider(lambda: ConnectionError("ECONNREFUSED")),
        "b": _OkProvider(),
    }
    monkeypatch.setattr(orch_mod, "get_provider", lambda n: chain[n])
    resp = await orch_mod.call_with_cascade(
        "p", primary="a", fallbacks=("b",), use_cache=False, tenant_id="t1"
    )
    assert resp.text == "ok"


@pytest.mark.asyncio
async def test_timeout_error_falls_through_to_next_provider(monkeypatch):
    """UAT-014 — asyncio.TimeoutError must be treated as transient."""
    await orch_mod.default_cache.clear()
    chain = {
        "a": _RaisingProvider(asyncio.TimeoutError),
        "b": _OkProvider(),
    }
    monkeypatch.setattr(orch_mod, "get_provider", lambda n: chain[n])
    resp = await orch_mod.call_with_cascade(
        "p", primary="a", fallbacks=("b",), use_cache=False, tenant_id="t2"
    )
    assert resp.text == "ok"


@pytest.mark.asyncio
async def test_httpx_error_falls_through_to_next_provider(monkeypatch):
    """UAT-014 — httpx.HTTPError must be treated as transient."""
    await orch_mod.default_cache.clear()
    chain = {
        "a": _RaisingProvider(lambda: httpx.ConnectError("nope")),
        "b": _OkProvider(),
    }
    monkeypatch.setattr(orch_mod, "get_provider", lambda n: chain[n])
    resp = await orch_mod.call_with_cascade(
        "p", primary="a", fallbacks=("b",), use_cache=False, tenant_id="t3"
    )
    assert resp.text == "ok"


@pytest.mark.asyncio
async def test_all_providers_down_raises_503_with_chain(monkeypatch):
    """UAT-044 — when the whole chain fails, surface HTTP 503 with the
    structured detail + Retry-After header instead of leaking the last
    ProviderError to the client as a 500."""
    await orch_mod.default_cache.clear()
    chain = {
        "a": _RaisingProvider(
            lambda: ProviderError("down", provider="a", transient=True)
        ),
        "b": _RaisingProvider(
            lambda: ProviderError("down", provider="b", transient=True)
        ),
    }
    monkeypatch.setattr(orch_mod, "get_provider", lambda n: chain[n])

    with pytest.raises(HTTPException) as info:
        await orch_mod.call_with_cascade(
            "p",
            primary="a",
            fallbacks=("b",),
            use_cache=False,
            tenant_id="t4",
        )

    assert info.value.status_code == 503
    assert info.value.detail["error"] == "providers_unavailable"
    assert info.value.detail["providers_tried"] == ["a", "b"]
    assert info.value.detail["retry_after"] == 60
    assert info.value.headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_first_provider_ok_returns_200(monkeypatch):
    """UAT-044 regression — single healthy provider still wins."""
    await orch_mod.default_cache.clear()
    monkeypatch.setattr(orch_mod, "get_provider", lambda _n: _OkProvider())
    resp = await orch_mod.call_with_cascade(
        "p", primary="ok", use_cache=False, tenant_id="t5"
    )
    assert resp.text == "ok"
