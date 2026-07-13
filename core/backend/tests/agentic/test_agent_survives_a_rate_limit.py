"""A rate-limited provider must end the turn, not kill the stream.

Found by the live scenario suite, not by a unit test: on a busy run the free
providers start returning 429, the cascade gives up with a structured 503, and
in agent mode that exception was raised from *inside* an SSE generator that had
already started streaming. Starlette's answer to that is

    RuntimeError: Caught handled exception, but response already started.

and the customer's answer to it is a chat that spins forever and never says
why. The loop caught ProviderError — the all-permanent case — and not the 503,
which is the case that actually happens when you are simply asking too fast.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.agentic import loop as loop_mod


async def _drain(**kw):
    return [e async for e in loop_mod.run_agent_loop(**kw)]


ARGS = dict(
    user_message="what is the system status?",
    providers=["groq", "gemini"],
    tenant="default",
    requester="admin@local",
)


@pytest.mark.asyncio
async def test_rate_limited_providers_end_the_turn_with_an_error_event(monkeypatch):
    async def _rate_limited(*_a, **_kw):
        raise HTTPException(
            status_code=503,
            detail={"error": "providers_unavailable", "last_error": "Gemini rate limit"},
        )

    monkeypatch.setattr(loop_mod, "_ask", _rate_limited)

    events = await _drain(**ARGS)

    # It ends, and it ends by saying so. Nothing escapes the generator.
    assert events, "the loop produced no events at all"
    last = events[-1]
    assert last.type == "agent-error"
    assert last.data["reason"] == "all_providers_failed"


@pytest.mark.asyncio
async def test_a_permanent_failure_ends_the_turn_the_same_way(monkeypatch):
    # The other shape the cascade raises. Same outcome for the person waiting.
    from app.providers.schemas import ProviderError

    async def _dead(*_a, **_kw):
        raise ProviderError("no key configured")

    monkeypatch.setattr(loop_mod, "_ask", _dead)

    events = await _drain(**ARGS)
    assert events[-1].type == "agent-error"
    assert events[-1].data["reason"] == "all_providers_failed"
