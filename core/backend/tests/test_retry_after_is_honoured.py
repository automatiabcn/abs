"""A provider's Retry-After reaches the cascade's second pass.

CI, 2026-08-28: Groq's free tier answered a burst with 429 twice, four
seconds apart, then 200 at thirty seconds. The provider had said how long to
wait; the error dropped it and the second pass came too early. The header
now rides on `ProviderError.retry_after`, and the pass waits for it (capped).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.cascade import orchestrator
from app.providers import base
from app.providers.schemas import ProviderError, ProviderResponse


def test_retry_after_header_is_parsed():
    assert base._retry_after_seconds(SimpleNamespace(headers={"retry-after": "7"})) == 7.0
    assert base._retry_after_seconds(SimpleNamespace(headers={"retry-after": "2.5"})) == 2.5
    assert base._retry_after_seconds(SimpleNamespace(headers={})) is None
    assert base._retry_after_seconds(SimpleNamespace(headers={"retry-after": "soon"})) is None


def test_provider_error_carries_retry_after():
    e = ProviderError("groq rate limit", provider="groq", transient=True, retry_after=6.0)
    assert e.retry_after == 6.0
    assert ProviderError("x").retry_after is None


class _BusyWithHintThenOk:
    def __init__(self, hint):
        self.calls = 0
        self.hint = hint

    async def call(self, prompt, model=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise ProviderError("groq rate limit", provider="groq", transient=True, retry_after=self.hint)
        return ProviderResponse(text="answer", provider="groq", model="m", elapsed_ms=1)


@pytest.mark.asyncio
async def test_second_pass_waits_for_the_hint_not_the_floor(monkeypatch):
    waited = []

    async def _sleep(s):
        waited.append(s)

    monkeypatch.setattr(orchestrator.asyncio, "sleep", _sleep)
    monkeypatch.setattr(orchestrator, "RATE_LIMIT_SECOND_PASS_S", 4.0)
    prov = _BusyWithHintThenOk(9.0)
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: prov)
    resp = await orchestrator.call_with_cascade("x", primary="groq", use_cache=False, tenant_id="t_ra_1")
    assert resp.text == "answer"
    assert waited == [9.0]


@pytest.mark.asyncio
async def test_hint_is_capped_and_floor_applies_without_one(monkeypatch):
    waited = []

    async def _sleep(s):
        waited.append(s)

    monkeypatch.setattr(orchestrator.asyncio, "sleep", _sleep)
    monkeypatch.setattr(orchestrator, "RATE_LIMIT_SECOND_PASS_S", 4.0)
    monkeypatch.setattr(orchestrator, "RATE_LIMIT_HINT_CAP_S", 20.0)
    capped = _BusyWithHintThenOk(600.0)
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: capped)
    await orchestrator.call_with_cascade("x", primary="groq", use_cache=False, tenant_id="t_ra_2")
    silent = _BusyWithHintThenOk(None)
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: silent)
    await orchestrator.call_with_cascade("x", primary="groq", use_cache=False, tenant_id="t_ra_3")
    assert waited == [20.0, 4.0]
