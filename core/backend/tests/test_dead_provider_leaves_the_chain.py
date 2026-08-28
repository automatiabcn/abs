# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""A provider that failed permanently stops leading the chain.

Live, 2026-08-28: a Cerebras key that had answered 402 for ten days was
still the first leg of every chat question. The health record knew
("permanent": true); the breaker did not care (it counts transient failures
in a window); the chain never asked. Every answer paid a dead leg first.
"""

from __future__ import annotations

import time

import pytest

from app.cascade import provider_health as health
from app.providers.base import BaseProvider
from app.providers.schemas import ProviderError, ProviderResponse


@pytest.fixture(autouse=True)
def _clean():
    health.reset_for_tests()
    yield
    health.reset_for_tests()


class _Ok(BaseProvider):
    default_model = "m"

    def __init__(self, name):
        self.name = name
        self.calls = 0

    async def call(self, prompt, model=None, **kw):
        self.calls += 1
        return ProviderResponse(text=f"from {self.name}", model="m", provider=self.name)


class _Dead(BaseProvider):
    default_model = "m"

    def __init__(self, name):
        self.name = name
        self.calls = 0

    async def call(self, prompt, model=None, **kw):
        self.calls += 1
        raise ProviderError("402 payment required", provider=self.name, transient=False)


def _wire(monkeypatch, providers):
    from app.cascade import orchestrator as orch

    table = {p.name: p for p in providers}
    monkeypatch.setattr(orch, "get_provider", lambda name: table[name])
    monkeypatch.setattr(orch, "_resolve_owner_key", lambda *a, **k: None)


def test_a_fresh_permanent_verdict_skips_the_provider_but_an_old_one_probes_it():
    health.note_failure("cerebras", tenant="t", permanent=True, detail="402")
    assert health.should_skip("cerebras", "t") is True
    # Ten minutes later it earns one more try.
    o = health.last("cerebras", "t")
    health._LAST[health._key("t", "cerebras")] = health.Outcome(
        False, True, o.detail, time.time() - health.PROBE_AFTER_S - 1, ""
    )
    assert health.should_skip("cerebras", "t") is False
    # A transient failure is never a reason to skip.
    health.note_failure("groq", tenant="t", permanent=False, detail="429")
    assert health.should_skip("groq", "t") is False


@pytest.mark.asyncio
async def test_the_dead_leg_is_not_called_while_its_verdict_stands(monkeypatch):
    from app.cascade.orchestrator import call_with_cascade, stream_with_cascade

    dead, ok = _Dead("cerebras"), _Ok("gemini")
    _wire(monkeypatch, [dead, ok])
    # First call: nobody knows yet, the dead leg is tried and fails.
    r = await call_with_cascade("q", primary="cerebras", fallbacks=("gemini",), use_cache=False, tenant_id="t")
    assert r.text == "from gemini" and dead.calls == 1
    # Second call: the verdict stands; the dead leg is not even tried.
    r = await call_with_cascade("q2", primary="cerebras", fallbacks=("gemini",), use_cache=False, tenant_id="t")
    assert r.text == "from gemini" and dead.calls == 1
    assert r.providers_tried == ["gemini"]
    # The stream asks the same question.
    events = [e async for e in stream_with_cascade("q3", primary="cerebras", fallbacks=("gemini",), use_cache=False, tenant_id="t")]
    assert [e["name"] for e in events if e["type"] == "provider"] == ["gemini"]
    assert not [e for e in events if e["type"] == "leg_failed"]
    assert dead.calls == 1


@pytest.mark.asyncio
async def test_a_chain_of_only_dead_legs_is_still_tried_so_the_error_is_real(monkeypatch):
    from app.cascade.orchestrator import call_with_cascade

    dead = _Dead("cerebras")
    _wire(monkeypatch, [dead])
    health.note_failure("cerebras", tenant="t", permanent=True, detail="402")
    with pytest.raises(ProviderError):
        await call_with_cascade("q", primary="cerebras", use_cache=False, tenant_id="t")
    assert dead.calls == 1, "the only provider must be tried, not silently skipped"


def test_a_new_key_clears_the_verdict():
    health.note_failure("cerebras", tenant="t", permanent=True, detail="402")
    health.forget("cerebras", tenant="t")
    assert health.should_skip("cerebras", "t") is False
    assert health.degraded_reason("cerebras", "t") == ""
