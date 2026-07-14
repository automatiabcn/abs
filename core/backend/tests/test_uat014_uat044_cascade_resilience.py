"""Cascade non-ProviderError fallback +
503 + structured detail when every provider is down."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.cascade import orchestrator as orch_mod
from app.providers.base import BaseProvider
from app.providers.schemas import (
    CascadeUnavailable,
    ProviderError,
    ProviderResponse,
)


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
    """ConnectionError used to bypass cascade and raise 500."""
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
    """asyncio.TimeoutError must be treated as transient."""
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
    """httpx.HTTPError must be treated as transient."""
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
    """When the whole chain fails, surface HTTP 503 with the
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

    # The claim is unchanged — an HTTP caller sees a structured 503 with a
    # Retry-After, not a leaked 500. What changed is where it is built: the
    # cascade raises a ProviderError (`CascadeUnavailable`) and the app's
    # exception handler turns it into the response. The cascade is called by
    # agents, MCP tools and workers that live nowhere near a web request, and
    # raising FastAPI's own exception at them meant it sailed past every
    # `except ProviderError` they had.
    with pytest.raises(CascadeUnavailable) as info:
        await orch_mod.call_with_cascade(
            "p",
            primary="a",
            fallbacks=("b",),
            use_cache=False,
            tenant_id="t4",
        )

    assert info.value.transient is True, "callers must know this one may recover"
    detail = info.value.detail()
    assert detail["error"] == "providers_unavailable"
    assert detail["providers_tried"] == ["a", "b"]
    assert detail["retry_after"] == 60
    assert info.value.retry_after == 60


def test_an_http_caller_still_gets_the_structured_503(monkeypatch):
    """The other half of the fallback contract, tested where it now happens.

    Moving the 503 out of the cascade and into an exception handler is only safe
    if the response is identical. So: drive the app itself, with every provider
    down, and check the customer's client sees exactly what it saw before —
    status, body, and the Retry-After it backs off on.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import app as real_app  # registers the handler

    probe = FastAPI(exception_handlers=real_app.exception_handlers)

    @probe.get("/boom")
    async def _boom():  # noqa: ANN202
        raise CascadeUnavailable(
            "everything is down",
            providers_tried=["groq", "gemini"],
            last_error=ProviderError("rate limit", provider="groq"),
        )

    resp = TestClient(probe, raise_server_exceptions=False).get("/boom")

    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "60"
    body = resp.json()["detail"]
    assert body["error"] == "providers_unavailable"
    assert body["providers_tried"] == ["groq", "gemini"]
    assert "rate limit" in body["last_error"]


@pytest.mark.asyncio
async def test_first_provider_ok_returns_200(monkeypatch):
    """Regression — single healthy provider still wins."""
    await orch_mod.default_cache.clear()
    monkeypatch.setattr(orch_mod, "get_provider", lambda _n: _OkProvider())
    resp = await orch_mod.call_with_cascade(
        "p", primary="ok", use_cache=False, tenant_id="t5"
    )
    assert resp.text == "ok"
