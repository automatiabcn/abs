"""A chain whose every leg was rate-limited gets one more pass.

CI scenarios, 2026-08-28: the server had one provider (a free Groq key), the
per-minute limit fired seven times in eight minutes, and each time the
cascade answered "every provider in the chain failed" — while the same key
answered 200 seconds later. That is the first install every customer makes.
One short pause and one more pass turn a 429 back into an answer; a
permanent failure and a second 429 still fail, and the pass never repeats.
"""

from __future__ import annotations

import pytest

from app.cascade import orchestrator
from app.providers.schemas import CascadeUnavailable, ProviderError, ProviderResponse


class _BusyThenOk:
    def __init__(self):
        self.calls = 0

    async def call(self, prompt, model=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise ProviderError("groq rate limit", provider="groq", transient=True)
        return ProviderResponse(text="answer", provider="groq", model="m", elapsed_ms=1)


class _AlwaysBusy:
    def __init__(self):
        self.calls = 0

    async def call(self, prompt, model=None, **kwargs):
        self.calls += 1
        raise ProviderError("HTTP 429 Too Many Requests", provider="groq", transient=True)


class _Down:
    def __init__(self):
        self.calls = 0

    async def call(self, prompt, model=None, **kwargs):
        self.calls += 1
        raise ProviderError("temporarily down", provider="groq", transient=True)


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(orchestrator, "RATE_LIMIT_SECOND_PASS_S", 0.0)


@pytest.mark.asyncio
async def test_a_rate_limited_single_provider_is_tried_once_more(monkeypatch):
    prov = _BusyThenOk()
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: prov)
    resp = await orchestrator.call_with_cascade("x", primary="groq", use_cache=False, tenant_id="t_rl_1")
    assert resp.text == "answer"
    assert prov.calls == 2


@pytest.mark.asyncio
async def test_still_busy_fails_after_exactly_one_more_pass(monkeypatch):
    prov = _AlwaysBusy()
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: prov)
    with pytest.raises(CascadeUnavailable):
        await orchestrator.call_with_cascade("x", primary="groq", use_cache=False, tenant_id="t_rl_2")
    assert prov.calls == 2


@pytest.mark.asyncio
async def test_a_transient_failure_that_is_not_a_rate_limit_gets_no_second_pass(monkeypatch):
    prov = _Down()
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: prov)
    with pytest.raises(CascadeUnavailable):
        await orchestrator.call_with_cascade("x", primary="groq", use_cache=False, tenant_id="t_rl_3")
    assert prov.calls == 1


class _StreamBusyThenOk:
    def __init__(self):
        self.calls = 0
        self.streams = True

    def stream(self, prompt, model=None, **kwargs):
        self.calls += 1
        n = self.calls
        outer = self

        class _Leg:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if n == 1:
                    raise ProviderError("groq rate limit", provider="groq", transient=True)
                raise StopAsyncIteration

            async def aclose(self):
                pass

        return _Leg()


@pytest.mark.asyncio
async def test_streaming_gets_the_second_pass_only_before_any_token(monkeypatch):
    prov = _StreamBusyThenOk()
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: prov)
    events = []
    try:
        async for ev in orchestrator.stream_with_cascade("x", primary="groq", use_cache=False, tenant_id="t_rl_4"):
            events.append(ev["type"])
    except CascadeUnavailable:
        pass
    assert prov.calls == 2, "the stream was not tried a second time after a rate limit"
    assert events.count("leg_failed") >= 1
