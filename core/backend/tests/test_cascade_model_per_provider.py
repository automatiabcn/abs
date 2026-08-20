# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""One model name cannot be right for every provider in a chain.

`call_with_cascade` took a single `model` and handed it to every leg. That was
harmless while callers passed None — each adapter used its own default — and it
became a trap the moment a caller pinned one, which the Composer did on
2026-08-02 to stop running on an 8B model.

Pinning the primary's model would have sent Groq's `openai/gpt-oss-120b` to
Gemini and Cohere on failover, where it does not exist: a guaranteed 404 on
every fallback leg. The fix for "the model is too weak" would have broken the
thing the product leads with — the agent that does not stop when a provider
does. Caught by auditing the fix rather than by the fix's own tests, which
only ever exercised one provider.

So the chain takes a map: each provider is asked for a model it actually
serves, and a provider missing from the map keeps its own default.
"""

from __future__ import annotations

import pytest

from app.cascade import orchestrator
from app.providers.schemas import ProviderError, ProviderResponse


class _Recorder:
    """A provider that records the model it was asked for."""

    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name = name
        self.default_model = f"{name}-default"
        self._fail = fail
        self.seen: list = []

    async def call(self, prompt: str, model=None, **kwargs):  # noqa: ANN001
        self.seen.append(model)
        if self._fail:
            raise ProviderError(f"{self.name} down", provider=self.name, transient=True)
        return ProviderResponse(
            text="ok", provider=self.name, model=model or self.default_model
        )


@pytest.fixture
def wired(monkeypatch):
    providers = {
        "groq": _Recorder("groq", fail=True),
        "gemini": _Recorder("gemini"),
    }
    monkeypatch.setattr(orchestrator, "get_provider", lambda n: providers[n])

    async def _allow(_key):
        return True

    monkeypatch.setattr(orchestrator.default_breaker, "allow", _allow)

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(orchestrator.default_breaker, "record_failure", _noop)
    monkeypatch.setattr(orchestrator.default_breaker, "record_success", _noop)
    return providers


@pytest.mark.asyncio
async def test_each_leg_is_asked_for_a_model_it_serves(wired):
    resp = await orchestrator.call_with_cascade(
        "hello",
        primary="groq",
        fallbacks=("gemini",),
        models={"groq": "openai/gpt-oss-120b", "gemini": "gemini-2.5-flash"},
        use_cache=False,
    )
    assert wired["groq"].seen == ["openai/gpt-oss-120b"]
    assert wired["gemini"].seen == ["gemini-2.5-flash"], (
        "the fallback was asked for the primary's model — a guaranteed 404"
    )
    assert resp.provider == "gemini"


@pytest.mark.asyncio
async def test_a_provider_missing_from_the_map_keeps_its_default(wired):
    await orchestrator.call_with_cascade(
        "hello",
        primary="groq",
        fallbacks=("gemini",),
        models={"groq": "openai/gpt-oss-120b"},
        use_cache=False,
    )
    assert wired["gemini"].seen == [None], (
        "a model name was invented for a provider we have no pin for"
    )


@pytest.mark.asyncio
async def test_the_old_single_model_still_works(wired):
    """Callers that pin one model for a one-provider chain are unaffected."""
    await orchestrator.call_with_cascade(
        "hello", primary="groq", fallbacks=("gemini",), model="shared", use_cache=False
    )
    assert wired["groq"].seen == ["shared"]
    assert wired["gemini"].seen == ["shared"]


@pytest.mark.asyncio
async def test_the_map_wins_over_the_single_model(wired):
    await orchestrator.call_with_cascade(
        "hello",
        primary="groq",
        fallbacks=("gemini",),
        model="shared",
        models={"gemini": "gemini-2.5-flash"},
        use_cache=False,
    )
    assert wired["groq"].seen == ["shared"], "no pin for groq, so the shared one"
    assert wired["gemini"].seen == ["gemini-2.5-flash"]
