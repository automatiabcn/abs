"""A rejected generation gets one immediate second pass.

Scenarios G1 and C10, 2026-08-28: Groq rejected its own model's JSON /
tool-call output (400 json_validate_failed, "could not be parsed"). Classing
that as transient stopped provider_health from parking Groq, but with one
provider in the chain there was no next leg, and the run still ended
"every provider failed". The failure is stochastic; the same request usually
succeeds on the next try — so the chain is tried once more, without the
rate-limit pause.
"""

from __future__ import annotations

import pytest

from app.cascade import orchestrator
from app.providers.schemas import CascadeUnavailable, ProviderError, ProviderResponse

REJECTED = 'groq 400: {"error":{"message":"Failed to validate JSON.","code":"json_validate_failed","failed_generation":""}}'


class _RejectThenOk:
    def __init__(self):
        self.calls = 0

    async def call(self, prompt, model=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise ProviderError(REJECTED, provider="groq", transient=True)
        return ProviderResponse(text='{"ok":true}', provider="groq", model="m", elapsed_ms=1)


class _AlwaysRejects:
    def __init__(self):
        self.calls = 0

    async def call(self, prompt, model=None, **kwargs):
        self.calls += 1
        raise ProviderError(REJECTED, provider="groq", transient=True)


@pytest.mark.asyncio
async def test_rejected_generation_is_retried_without_waiting(monkeypatch):
    waited = []

    async def _sleep(s):
        waited.append(s)

    monkeypatch.setattr(orchestrator.asyncio, "sleep", _sleep)
    prov = _RejectThenOk()
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: prov)
    resp = await orchestrator.call_with_cascade("x", primary="groq", use_cache=False, tenant_id="t_gen_1")
    assert resp.text == '{"ok":true}'
    assert prov.calls == 2
    assert waited == [0.0]


@pytest.mark.asyncio
async def test_a_second_rejection_still_fails_and_never_loops(monkeypatch):
    async def _sleep(s):
        return None

    monkeypatch.setattr(orchestrator.asyncio, "sleep", _sleep)
    prov = _AlwaysRejects()
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: prov)
    with pytest.raises(CascadeUnavailable):
        await orchestrator.call_with_cascade("x", primary="groq", use_cache=False, tenant_id="t_gen_2")
    assert prov.calls == 2
