# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Bringing your own key has to change who answers you.

The server's default is free-first, deliberately: the operator's bill stays at
zero and the free tier is meant to be good enough that most people never look
past it. That ordering is right for the operator's *own* keys.

It was also being applied to keys the *user* had pasted in. So someone who
brought their own Anthropic key — the one paid provider in the chain — had it
sorted last, behind every free provider, and was answered by the free tier
anyway. They had bought nothing. Nothing errored; the key simply never came up.

Pasting a key is a statement of preference. These tests hold both halves of that:
the key you bring is the one that answers you, and the person who brings nothing
still gets the free chain, exactly as before.
"""

from __future__ import annotations

import pytest

from app.providers import cascade as cascade_mod
from app.providers.cascade import PAID_PROVIDERS, get_active_providers

REAL = "a-real-looking-key-AAAAAAAA"


@pytest.fixture()
def operator_has_free_keys(monkeypatch):
    """The ordinary install: the operator configured the free providers."""
    for attr in ("groq_api_key", "gemini_api_key"):
        monkeypatch.setattr(cascade_mod.settings, attr, REAL)
    for attr in (
        "anthropic_api_key",
        "cerebras_api_key",
        "cohere_api_key",
        "cf_api_token",
    ):
        monkeypatch.setattr(cascade_mod.settings, attr, "")
    monkeypatch.setattr(cascade_mod.settings, "cf_account_id", "")


class TestTheKeyYouBringIsTheOneThatAnswersYou:
    def test_a_brought_paid_key_is_used_first_not_last(self, operator_has_free_keys):
        # anthropic is the paid provider and sorts last by default. A user who
        # pastes their own Anthropic key is asking to be answered by it.
        chain = get_active_providers(extra_configured=frozenset({"anthropic"}))
        assert chain[0] == "anthropic", chain
        # And the operator's free providers are still there, behind it, as the
        # fallback they were always meant to be.
        assert "groq" in chain

    def test_a_brought_key_activates_a_provider_the_server_never_configured(
        self, operator_has_free_keys
    ):
        chain = get_active_providers(extra_configured=frozenset({"cerebras"}))
        assert chain[0] == "cerebras"

    def test_several_brought_keys_keep_their_usual_order_among_themselves(
        self, operator_has_free_keys
    ):
        chain = get_active_providers(
            extra_configured=frozenset({"anthropic", "cerebras"})
        )
        # Both ahead of the operator's providers; between themselves, the house
        # ordering still applies rather than something arbitrary.
        assert set(chain[:2]) == {"anthropic", "cerebras"}
        assert chain.index("groq") > 1


class TestTheFreeDefaultIsNotDisturbed:
    def test_bringing_nothing_leaves_the_free_chain_exactly_as_it_was(
        self, operator_has_free_keys
    ):
        chain = get_active_providers()
        assert chain[0] == "groq"
        assert all(p not in PAID_PROVIDERS for p in chain)

    def test_asking_for_free_only_wins_even_over_a_key_you_brought(
        self, operator_has_free_keys
    ):
        # skip_paid is someone saying "keep me on the free tier". They mean it,
        # key or no key — the switch is not a budget guess we get to overrule.
        chain = get_active_providers(
            skip_paid=True, extra_configured=frozenset({"anthropic"})
        )
        assert "anthropic" not in chain
        assert chain[0] == "groq"

    def test_an_explicit_preference_still_beats_everything(
        self, operator_has_free_keys
    ):
        chain = get_active_providers(
            prefer="gemini", extra_configured=frozenset({"anthropic"})
        )
        assert chain[0] == "gemini"  # asked for by name, on this request


class TestTheAgentRuntimeHonoursItToo:
    def test_agents_pass_the_callers_keys_into_the_chain(self):
        # The chat path already did; an agent run that didn't would answer from
        # the free tier while the person's paid key sat unused.
        import inspect

        from app.agents import runtime

        source = inspect.getsource(runtime._complete)
        assert "tenant_configured_providers" in source
        assert "extra_configured=extra" in source
