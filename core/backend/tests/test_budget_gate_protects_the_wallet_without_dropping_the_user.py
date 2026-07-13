# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The budget gate has two jobs, and the second one is easy to forget.

The first is to protect the customer's money: when the monthly Claude budget is
spent, refuse to spend more. That part is well covered — the gate raises, before
the network call, and a pile of unit tests say so.

The second is to not punish the customer for it. A gate that protects the wallet
by handing the user an error has traded a bill for an outage, and the person who
set the budget did not ask for that. The cascade exists precisely so this is not
the trade: Anthropic goes quiet, a free provider answers, and the only thing the
customer loses is a model tier.

Nothing tested that. The gate was tested against itself, and the cascade was
tested against providers that fail for other reasons. This is the join: over
budget, still answered, and not one token of Claude spent.
"""

from __future__ import annotations

import pathlib

import pytest

from app.observability import quota_monitor as qm
from app.providers.schemas import ProviderError, ProviderResponse


@pytest.fixture()
def spent_ledger(tmp_path, monkeypatch) -> pathlib.Path:
    """A month whose Claude budget is already gone, on a server that has Claude
    switched on and keyed — the only configuration in which any of this matters."""
    from app.config import settings

    path = tmp_path / "claude.jsonl"
    monkeypatch.setenv("ABS_CLAUDE_QUOTA_LEDGER", str(path))
    monkeypatch.setenv("ABS_CLAUDE_MONTHLY_TOKEN_LIMIT", "1000")
    monkeypatch.setenv("ABS_CLAUDE_QUOTA_BLOCK_PCT", "0.95")
    # Claude switched on *in settings*, not just in the environment: settings are
    # already loaded by now, and an env var alone would leave the adapter refusing
    # on the opt-in check instead of the budget. The tests below would still be
    # green — for entirely the wrong reason.
    monkeypatch.setattr(settings, "anthropic_enabled", True, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-key", raising=False)
    monkeypatch.setattr(settings, "anthropic_mock_mode", "off", raising=False)
    qm.reset_for_tests()
    qm.record(tokens_in=980, tokens_out=0, model="claude-test", ledger=path)
    return path


@pytest.mark.asyncio
async def test_over_budget_the_user_still_gets_an_answer_and_claude_is_never_called(
    spent_ledger, monkeypatch
):
    """Anthropic is refused locally; a free provider picks the request up.

    The Anthropic side is the *real* provider, not a stand-in: a stub that
    imitates the gate would only prove my imitation of it is correct. The one
    thing stubbed out is the Anthropic SDK itself, so that a network call — if
    one were ever made — is loud and countable instead of a billed request.
    """
    from app.cascade import orchestrator
    from app.providers.anthropic.adapter import AnthropicProvider

    network = {"anthropic_calls": 0, "groq_calls": 0}

    def _explode(*a, **k):  # noqa: ANN001, ANN002
        network["anthropic_calls"] += 1
        raise AssertionError("Claude was called with the budget already spent")

    monkeypatch.setattr("anthropic.AsyncAnthropic", _explode, raising=False)

    class _Groq:
        name = "groq"
        default_model = "llama-free"

        async def call(self, prompt, model=None, **kwargs):  # noqa: ANN001
            network["groq_calls"] += 1
            return ProviderResponse(
                text="a perfectly good free answer", provider="groq", model="llama-free"
            )

    def _get(name: str):
        return {"anthropic": AnthropicProvider(), "groq": _Groq()}[name]

    # The orchestrator resolves providers through `get_provider`; patch it there
    # so the chain walks these two and touches no network at all.
    monkeypatch.setattr(orchestrator, "get_provider", _get)

    resp = await orchestrator.call_with_cascade(
        "a question somebody paid for a server to answer",
        primary="anthropic",
        fallbacks=("groq",),
        tenant_id="default",
        max_tokens=256,
    )

    assert resp.text == "a perfectly good free answer"
    assert resp.provider == "groq", "the budget gate turned into an outage"
    assert network["anthropic_calls"] == 0, "spent money that was already gone"
    assert network["groq_calls"] == 1


@pytest.mark.asyncio
async def test_the_gate_refuses_before_the_network_call(spent_ledger):
    """Order matters more than the refusal does.

    Refusing after the request has gone out protects nothing: the tokens are
    already billed. The gate must be the reason no request is made, not a note
    written about one that was.
    """
    with pytest.raises(qm.QuotaExceeded):
        qm.gate(requested_tokens=100, ledger=spent_ledger)


@pytest.mark.asyncio
async def test_a_quota_refusal_is_transient_so_the_chain_keeps_walking(
    spent_ledger, monkeypatch
):
    """A budget block is not "this provider is broken" — it is "not this one,
    not now". It has to be classified as transient, or the cascade treats it as
    a permanent failure and stops walking the chain, and the customer gets the
    error we were trying to spare them."""
    from app.providers.anthropic.adapter import AnthropicProvider

    with pytest.raises(ProviderError) as exc:
        await AnthropicProvider().call("anything", max_tokens=256)

    assert exc.value.transient is True, (
        "a quota block read as a permanent failure — the cascade would give up "
        "instead of falling through to a free provider"
    )
