# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The usage page was counting one caller and ignoring the product.

Metering lived in the `/v1/cascade/run` route, so it recorded requests made
through that API and nothing else. Chat — the surface the whole product is built
around — goes through the cascade without going through that route, and so did
agents, workflows and RAG answers. None of them were counted.

The effect was not an empty page. It was a *plausible* page: real numbers, real
provider mix, a real free-path percentage, all computed over a slice of traffic
that excluded almost everything the customer had actually done. Somebody
watching their spend was reading a figure that ignored their week.

Metering now happens inside the cascade, at the single point every answered
request passes through, and only there.
"""

from __future__ import annotations

import pytest

from app.providers.schemas import ProviderResponse


@pytest.fixture()
def recorded(monkeypatch):
    """Capture what gets metered, without touching the DB."""
    rows: list[dict] = []

    def _append(provider, tokens=0, *, tenant_slug="default", **kw):  # noqa: ANN001
        rows.append({"provider": provider, "tokens": tokens, "tenant": tenant_slug})

    from app.services import usage_log

    monkeypatch.setattr(usage_log, "append", _append)
    return rows


def _provider(name: str, tokens_in: int = 10, tokens_out: int = 5):
    class _P:
        default_model = "m"

        async def call(self, prompt, model=None, **kwargs):  # noqa: ANN001
            return ProviderResponse(
                text="answer",
                provider=name,
                model="m",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )

    _P.name = name
    return _P()


@pytest.mark.asyncio
async def test_an_answer_is_metered_wherever_it_was_asked_for(recorded, monkeypatch):
    """Chat does not call the cascade *route*; it calls the cascade. Counting at
    the route meant counting almost nothing."""
    from app.cascade import orchestrator

    monkeypatch.setattr(orchestrator, "get_provider", lambda n: _provider(n))

    resp = await orchestrator.call_with_cascade(
        "a question asked from chat, not from the API",
        primary="groq",
        tenant_id="acme",
        use_cache=False,
    )

    assert resp.provider == "groq"
    assert recorded == [{"provider": "groq", "tokens": 15, "tenant": "acme"}]


@pytest.mark.asyncio
async def test_the_provider_that_actually_answered_is_the_one_billed(
    recorded, monkeypatch
):
    """After a failover, the usage must name the provider that did the work.

    Attributing a Groq answer to the Anthropic that refused it would put free
    traffic in the paid column — and the free-path percentage is the number this
    product is sold on.
    """
    from app.cascade import orchestrator
    from app.providers.schemas import ProviderError

    class _Dead:
        name = "anthropic"
        default_model = "m"

        async def call(self, prompt, model=None, **kwargs):  # noqa: ANN001
            raise ProviderError("rate limited", provider="anthropic", transient=True)

    def _get(name: str):
        return _Dead() if name == "anthropic" else _provider(name)

    monkeypatch.setattr(orchestrator, "get_provider", _get)

    resp = await orchestrator.call_with_cascade(
        "anything",
        primary="anthropic",
        fallbacks=("groq",),
        tenant_id="acme",
        use_cache=False,
    )

    assert resp.provider == "groq"
    assert [r["provider"] for r in recorded] == ["groq"], (
        "the provider that failed was billed for the answer it did not give"
    )


@pytest.mark.asyncio
async def test_a_failed_request_is_not_counted_as_usage(recorded, monkeypatch):
    """Nobody was served, so nobody spent anything."""
    from app.cascade import orchestrator
    from app.providers.schemas import ProviderError

    class _Dead:
        name = "groq"
        default_model = "m"

        async def call(self, prompt, model=None, **kwargs):  # noqa: ANN001
            raise ProviderError("dead", provider="groq", transient=False)

    monkeypatch.setattr(orchestrator, "get_provider", lambda n: _Dead())

    with pytest.raises(Exception):
        await orchestrator.call_with_cascade(
            "anything",
            primary="groq",
            tenant_id="acme",
            use_cache=False,
        )

    assert recorded == [], "a request nobody answered was counted as usage"


@pytest.mark.asyncio
async def test_a_cached_answer_is_not_counted_twice(recorded, monkeypatch):
    """The second asker got the first asker's answer. No provider was called, so
    no provider call happened — the counter must say so, or a cache hit inflates
    the very number the cache exists to reduce."""
    from app.cascade import orchestrator

    monkeypatch.setattr(orchestrator, "get_provider", lambda n: _provider(n))

    for _ in range(2):
        await orchestrator.call_with_cascade(
            "the same question, twice",
            primary="groq",
            tenant_id="acme",
            use_cache=True,
        )

    assert len(recorded) == 1, "a cache hit was metered as a fresh provider call"


@pytest.mark.asyncio
async def test_a_call_with_no_caller_context_is_not_filed_under_a_phantom_tenant(
    recorded, monkeypatch
):
    """`_global` is the orchestrator's "nobody told me who is asking" marker —
    it is not a tenant. Recording it as one files the call under a slug no
    operator can ever look at, which is just a slower way of losing it."""
    from app.cascade import orchestrator

    monkeypatch.setattr(orchestrator, "get_provider", lambda n: _provider(n))

    await orchestrator.call_with_cascade(
        "a delegated MCP tool call, with no tenant attached",
        primary="groq",
        use_cache=False,
    )

    assert recorded[0]["tenant"] == "default"


@pytest.mark.asyncio
async def test_metering_failure_never_costs_the_customer_their_answer(monkeypatch):
    """The answer is the product. The bookkeeping is not."""
    from app.cascade import orchestrator
    from app.services import usage_log

    def _boom(*a, **k):  # noqa: ANN001, ANN002
        raise RuntimeError("the usage table is on fire")

    monkeypatch.setattr(usage_log, "append", _boom)
    monkeypatch.setattr(orchestrator, "get_provider", lambda n: _provider(n))

    resp = await orchestrator.call_with_cascade(
        "anything",
        primary="groq",
        tenant_id="acme",
        use_cache=False,
    )
    assert resp.text == "answer"
