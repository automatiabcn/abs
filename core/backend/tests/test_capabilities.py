# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""What an install can do, and whether it says so honestly.

ABS runs on the developer's own keys, so an install is never simply working or
broken — it sits somewhere on a slope. These tests hold the two rules that make
that slope readable:

* a capability counts as available only when it would really run, and
* every unavailable one names the cheapest real way to get it.

The second rule is not politeness. "Needs an embedding provider" leaves the
reader where they were; "Ollama is a free local install" is the difference
between a dead end and a next step.
"""

from __future__ import annotations

import pytest

from app.capabilities import (
    CAPABILITIES,
    FREE_TO_START,
    HOW_TO_GET,
    assess,
    summarise,
)


def by_key(states):
    return {s.capability.key: s for s in states}


def test_a_fresh_install_with_no_keys_offers_only_what_runs_locally():
    states = by_key(assess([]))
    # These need nothing but the machine, and must not be dressed up as
    # locked features a key would unlock.
    assert states["blast_radius"].available is True
    assert states["checks"].available is True
    # Everything that needs a provider is honestly unavailable.
    for key in ("ask", "edit", "judge", "failover", "second_opinion"):
        assert states[key].available is False, key
        assert states[key].unlock_with, f"{key} does not say how to unlock it"


def test_one_free_key_already_buys_the_core():
    states = by_key(assess(["groq"]))
    for key in ("ask", "edit", "judge"):
        assert states[key].available is True, key
    # But not the two that are meaningless with a single provider.
    assert states["failover"].available is False
    assert states["second_opinion"].available is False
    assert "1" in states["failover"].blocked_by or "is 1" in states["failover"].blocked_by


def test_a_second_provider_is_what_failover_and_disagreement_mean():
    states = by_key(assess(["groq", "cerebras"]))
    assert states["failover"].available is True
    assert states["second_opinion"].available is True


def test_a_knowledge_base_without_embeddings_is_reported_as_missing():
    # The backend falls back to hashes of the text: five chunks come back and
    # none of them relate to the question. Calling that a knowledge base is
    # the one failure mode worse than not having one.
    states = by_key(assess(["groq"], embedding_backend="mock"))
    know = states["knowledge"]
    assert know.available is False
    assert "hashes" in know.blocked_by or "meaning" in know.blocked_by
    assert know.unlock_is_free is True
    assert "ollama" in know.unlock_with


@pytest.mark.parametrize("backend", ["ollama", "cohere", "sentence_transformers"])
def test_any_real_embedding_source_is_enough(backend):
    states = by_key(assess(["groq"], embedding_backend=backend))
    assert states["knowledge"].available is True


def test_a_cohere_key_alone_answers_questions_and_embeds():
    # Cohere sits in the cascade order and answers chat (command-r-plus took a
    # live question on 2026-08-18) besides embedding and reranking. The old
    # premise here — "not a cascade answerer" — under-counted what a Cohere
    # key buys and hid a real failover.
    states = by_key(assess(["cohere"]))
    assert states["ask"].available is True
    assert states["knowledge"].available is True
    # …but not the judge: its pinned model is served only by groq/cerebras.
    assert states["judge"].available is False


def test_every_unavailable_capability_can_be_acted_on():
    for configured in ([], ["groq"], ["cohere"]):
        for state in assess(configured):
            if state.available:
                continue
            assert state.unlock_with, f"{state.capability.key}: nothing to do"
            assert state.blocked_by.endswith("."), state.capability.key
            assert state.how_to, f"{state.capability.key}: no way to obtain the key"


def test_every_named_key_has_somewhere_to_get_it():
    for provider in HOW_TO_GET:
        assert HOW_TO_GET[provider].strip()
    # A free key must say so where it matters — the reader's first question is
    # whether this costs money.
    for provider in FREE_TO_START:
        assert provider in HOW_TO_GET
        assert "Free" in HOW_TO_GET[provider] or "free" in HOW_TO_GET[provider]


def test_the_summary_names_the_single_most_useful_next_key():
    s = summarise(assess([]))
    assert s["ready"] < s["total"]
    assert s["next_key"], "an empty install must be told where to start"
    assert s["next_key_is_free"] is True, "the first suggestion should not cost money"
    assert s["next_key_how"]
    assert s["next_key_unlocks"], "a suggestion that unlocks nothing is not a suggestion"


def test_a_fully_configured_install_is_told_it_is_done():
    s = summarise(assess(["groq", "cerebras", "gemini"], embedding_backend="ollama"))
    assert s["ready"] == s["total"]
    assert s["blocked"] == []
    assert s["next_key"] == "", "nothing left to ask for"


def test_capabilities_describe_what_the_reader_gets():
    for cap in CAPABILITIES:
        assert cap.promise.endswith("."), cap.key
        # A promise that repeats the title teaches nothing.
        assert cap.promise.lower() != cap.title.lower()
        assert len(cap.promise) > len(cap.title)


# --- a key that exists but cannot answer right now ---------------------------
#
# Rate limits and open breakers are temporary. Counting a throttled provider
# would promise a failover that will not happen this minute; forgetting it had
# a key would send somebody to buy one they already own. Both are wrong, and
# they are wrong in opposite directions — which is why this distinction is
# tested rather than assumed.


def test_a_throttled_provider_does_not_count_toward_what_works():
    states = by_key(
        assess(["groq", "cerebras"], unusable_now={"cerebras": "is rate-limited"})
    )
    # Two keys, but only one can answer — so the two-provider capabilities are
    # honestly off.
    assert states["failover"].available is False
    assert states["second_opinion"].available is False
    # The one-provider capabilities still work, because one still answers.
    assert states["ask"].available is True
    assert states["edit"].available is True


def test_a_resting_provider_is_told_to_wait_not_to_buy():
    state = by_key(
        assess(["groq", "cerebras"], unusable_now={"cerebras": "is rate-limited"})
    )["failover"]
    assert "Not right now" in state.blocked_by
    assert "cerebras is rate-limited" in state.blocked_by
    assert "passes" in state.blocked_by, "the reader should know this fixes itself"
    # And crucially: no shopping list. Advising a purchase here would be
    # advising money spent on a problem that resolves on its own.
    assert state.unlock_with == []
    assert state.how_to == ""


def test_a_genuinely_missing_key_is_still_a_missing_key():
    # One provider, and it is resting: there is no second key to wait for, so
    # the honest answer really is "bring one".
    state = by_key(assess(["groq"], unusable_now={"groq": "is rate-limited"}))["failover"]
    assert "Needs 2 providers" in state.blocked_by
    assert state.unlock_with, "with nothing to wait for, say what to get"


def test_everything_throttled_still_leaves_the_local_work_alone():
    states = by_key(
        assess(["groq"], unusable_now={"groq": "breaker is open"}, embedding_backend="ollama")
    )
    # These never needed a provider and are unaffected by anyone's rate limit.
    assert states["blast_radius"].available is True
    assert states["checks"].available is True
    assert states["knowledge"].available is True
    # But asking a question needs somebody to ask.
    assert states["ask"].available is False
    assert "breaker is open" in states["ask"].blocked_by or states["ask"].unlock_with
