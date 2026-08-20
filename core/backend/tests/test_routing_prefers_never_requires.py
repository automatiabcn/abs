# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Routing is a preference. The install works with whatever it has.

Founder's rule (08-03): *the system runs at the best efficiency the resources
allow, subscription or no subscription.* That makes every route here an opinion
about suitability and never a requirement — an install with one free key does
everything that install can do, in the best order that key allows.

Which is why most of this file is about absence: what happens when the good
option is missing. A router that quietly refuses work because the ideal
provider is not connected would turn "bring what you have" into "bring what we
prefer", and the customer would find out at the worst moment.

The single exception is inline completion, and it is a kindness rather than a
refusal — see the test that says so.
"""

from __future__ import annotations

from app.cascade import routing as r

ALL = ["codex", "anthropic", "groq", "cerebras", "gemini", "ollama"]


# --- preference, never requirement ------------------------------------------


def test_one_free_key_still_does_everything():
    """The whole rule in one test."""
    for task in (r.INSTANT, r.QUICK, r.DEEP):
        assert r.chain_for(task, ["groq"]) == ["groq"], task


def test_deep_work_runs_without_a_subscription():
    chain = r.chain_for(r.DEEP, ["groq", "gemini"])
    assert chain, "deep work refused because no subscription was connected"
    assert chain[0] == "cerebras" if "cerebras" in chain else chain[0] == "groq"


def test_a_subscription_leads_deep_work_when_it_is_there():
    chain = r.chain_for(r.DEEP, ["groq", "codex"])
    assert chain[0] == "codex", "the strongest thing connected did not lead"
    assert "groq" in chain, "the fallback was dropped rather than demoted"


def test_nothing_connected_is_an_empty_chain_not_a_crash():
    assert r.chain_for(r.DEEP, []) == []
    assert r.chain_for(r.QUICK, ["", "  ", None]) == []


def test_every_available_provider_survives_somewhere():
    """A provider must never vanish because we had no opinion about it."""
    chain = r.chain_for(r.DEEP, ALL + ["some-new-vendor"])
    assert set(chain) == set(ALL + ["some-new-vendor"])
    assert chain[-1] == "some-new-vendor", (
        "a provider we have not thought about should run last, not be dropped"
    )


def test_duplicates_do_not_produce_duplicate_legs():
    assert r.chain_for(r.QUICK, ["groq", "GROQ", " groq "]) == ["groq"]
    # And for a provider we have no opinion about, where the de-duplication is
    # the only thing standing between one leg and three identical ones.
    assert r.chain_for(r.QUICK, ["newvendor", "NewVendor", "newvendor "]) == [
        "newvendor"
    ]


# --- the one refusal --------------------------------------------------------


def test_inline_completion_will_not_use_a_slow_provider():
    """A completion that lands seconds late is not a slow suggestion, it is a
    wrong one: the developer has typed the next line and the ghost text now
    describes the past."""
    assert r.chain_for(r.INSTANT, ["codex", "agy"]) == []
    assert "codex" not in r.chain_for(r.INSTANT, ["codex", "groq"])


def test_that_refusal_does_not_leak_into_the_other_two():
    """A subscription is exactly right for the deep work — refusing it there
    would throw away the strongest thing the customer has."""
    assert r.chain_for(r.DEEP, ["codex"]) == ["codex"]
    assert r.chain_for(r.QUICK, ["codex"]) == ["codex"]


def test_the_empty_instant_chain_says_why():
    msg = r.explain(r.INSTANT, [])
    assert "too slowly" in msg and "completion" in msg
    assert r.explain(r.DEEP, []) == "No provider is connected."


# --- ordering ---------------------------------------------------------------


def test_instant_wants_small_and_fast_not_strongest():
    chain = r.chain_for(r.INSTANT, ["anthropic", "groq"])
    assert chain[0] == "groq", (
        "a premium model was put on a keystroke path — money and latency spent "
        "on a suggestion that gets typed over"
    )


def test_deep_wants_strongest_first():
    chain = r.chain_for(r.DEEP, ["groq", "anthropic"])
    assert chain[0] == "anthropic"


def test_an_unknown_task_is_treated_as_the_middle_one():
    assert r.chain_for("something-else", ALL) == r.chain_for(r.QUICK, ALL)


def test_the_order_is_stable():
    a = r.chain_for(r.DEEP, ALL)
    b = r.chain_for(r.DEEP, list(reversed(ALL)))
    assert a == b, "the chain depended on the order the providers arrived in"


# --- readable ---------------------------------------------------------------


def test_the_panel_can_say_what_ran_and_why():
    """A routing decision the developer cannot read is the opaque-cost problem
    in a new place."""
    assert "already pay for" in r.explain(r.DEEP, ["codex", "groq"])
    assert "strongest" in r.explain(r.DEEP, ["anthropic", "groq"])
    assert "fastest" in r.explain(r.INSTANT, ["groq"])


# --- wired in ---------------------------------------------------------------


def test_the_composer_asks_for_the_deep_order(monkeypatch):
    """The hardest job must not inherit the cost-first order."""
    import asyncio

    from app.composer import runtime

    seen: dict = {}

    async def _fake(prompt, **kwargs):  # noqa: ANN001
        seen.update(kwargs)

        class _R:
            text = '{"summary": "", "edits": []}'
            provider = "codex"
            providers_tried = ["codex"]
            tokens_in = tokens_out = 0
            model = None

        return _R()

    monkeypatch.setattr(
        "app.cascade.orchestrator.call_with_cascade", _fake, raising=False
    )
    # Cost-first order would put the free key first; deep work wants the
    # strongest thing connected.
    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers",
        lambda **_k: ["groq", "anthropic"],
    )
    # The caller BROUGHT the anthropic key. A paid provider runs on the key of
    # the person asking (2026-08-18); the deep order then puts it first.
    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers",
        lambda **_k: {"anthropic"},
    )

    asyncio.run(
        runtime._generate_edits(
            "task", tenant_id="t", project_slug=None, user_subject="dev@example.com"
        )
    )
    assert seen.get("primary") == "anthropic", (
        "the Composer took the cheapest provider for the hardest job"
    )
    assert "groq" in tuple(seen.get("fallbacks") or ()), "the fallback was dropped"


def test_the_composer_still_runs_on_one_free_key(monkeypatch):
    """Founder's rule: no subscription, no premium key — it still works."""
    import asyncio

    from app.composer import runtime

    seen: dict = {}

    async def _fake(prompt, **kwargs):  # noqa: ANN001
        seen.update(kwargs)

        class _R:
            text = '{"summary": "", "edits": []}'
            provider = "groq"
            providers_tried = ["groq"]
            tokens_in = tokens_out = 0
            model = None

        return _R()

    monkeypatch.setattr(
        "app.cascade.orchestrator.call_with_cascade", _fake, raising=False
    )
    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers", lambda **_k: ["groq"]
    )

    parsed, _tried, _meta = asyncio.run(
        runtime._generate_edits(
            "task", tenant_id="t", project_slug=None, user_subject=None
        )
    )
    assert seen.get("primary") == "groq"
    assert parsed == {"summary": "", "edits": []}


def test_fim_orders_by_speed_not_by_cost(monkeypatch):
    """Tab is the one path where latency is the feature."""
    from app.fim import complete as fim

    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers",
        lambda **_k: ["cerebras", "groq"],
    )
    monkeypatch.setattr(fim, "_FAST_MODELS", {"groq": "m", "cerebras": "m"})
    chain = fim._free_fast_chain(tenant_id=None, user_subject=None)
    assert chain and chain[0] == "groq", "the fastest connected provider did not lead"


def test_fim_keeps_only_providers_it_can_prompt(monkeypatch):
    """Ordering is a routing opinion; "can we prompt this at all" is FIM's own
    constraint and must survive the reordering."""
    from app.fim import complete as fim

    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers",
        lambda **_k: ["anthropic", "groq"],
    )
    monkeypatch.setattr(fim, "_FAST_MODELS", {"groq": "m"})
    assert fim._free_fast_chain(tenant_id=None, user_subject=None) == ["groq"]
