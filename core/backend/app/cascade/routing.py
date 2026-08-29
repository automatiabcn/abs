# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Which provider should do which kind of work.

Until now the chain answered one question — who is configured — and every task
got the same order. That is right for cost and wrong for quality: a Tab
completion and a multi-file refactor are not the same job, and the provider
that suits one is the wrong choice for the other.

**A route is a preference, never a requirement.** This is the rule the whole
module is built around: whatever the developer brought, the work runs on the
best of it. A missing tier is skipped, not waited for; nothing here can refuse
a task because the ideal provider is absent. An install with one free key does
everything that install can do.

Three kinds of work, because three is what the difference actually is:

* **instant** — Tab completion. Latency IS the feature; an answer that arrives
  after the developer has typed the next line is worse than no answer at all.
  This is the one place a slow provider is not "better than nothing", and the
  only place this module will return an empty chain.
* **quick** — chat, explain a selection, a one-file review. Wants a fast, cheap
  model and does not need the strongest.
* **deep** — Composer proposals, the judge, whole-file work. The hardest thing
  we ask a model to do, and where a subscription the developer already pays for
  earns its place: slow to start, strong when it answers.

The tiers are ordered inside each class, and a provider that is in none of them
still runs — it lands after the ones we have an opinion about rather than being
dropped. Silence about a provider is not a judgement on it.
"""

from __future__ import annotations

from typing import Iterable, Sequence

# What a task is. Callers pass one of these; anything unknown is treated as
# `quick`, which is the middle and therefore the least wrong guess.
INSTANT = "instant"
QUICK = "quick"
DEEP = "deep"

# Providers whose first token takes seconds, not milliseconds: a subscription
# CLI has to start a process and often a session. Strong, and unusable on a
# keystroke path.
SLOW_START: frozenset[str] = frozenset({"codex", "agy", "claude_cli"})

# Preference per task class, best first. These are opinions about SUITABILITY,
# not about availability — nothing here implies any of them exist.
_PREFERENCE: dict[str, tuple[str, ...]] = {
    # Small, fast, free. A 120B model on a keystroke is money and latency spent
    # on a suggestion the developer will type over.
    INSTANT: ("groq", "cerebras", "mlx", "ollama"),
    QUICK: ("groq", "cerebras", "gemini", "cloudflare", "ollama", "mlx"),
    # Strongest first. Subscriptions lead because the developer already paid
    # for them and they are the strongest thing most installs will ever have.
    DEEP: (
        "codex",
        "claude_cli",
        "agy",
        "anthropic",
        "cerebras",
        "groq",
        # Gemini before OpenRouter: a Composer proposal is strict JSON with
        # whole files in it, and the free OpenRouter models answered with 33k
        # characters of prose that could not be read (live, 08-28), while
        # Gemini 2.5 Flash returns the object. OpenRouter stays as the last
        # cloud resort.
        "gemini",
        "openrouter",
        "ollama",
    ),
}


def chain_for(task: str, available: Iterable[str]) -> list[str]:
    """The order to try, for this kind of work, out of what exists.

    Never returns a provider that is not available, never invents one, and —
    except for `instant` — never returns empty while anything is available.
    """
    have = [str(p).strip().lower() for p in available if str(p or "").strip()]
    seen: set[str] = set()
    unique = [p for p in have if not (p in seen or seen.add(p))]
    if not unique:
        return []

    kind = task if task in _PREFERENCE else QUICK

    if kind == INSTANT:
        # The one refusal in this module, and it is a kindness: a completion
        # that lands seconds late is not a slow suggestion, it is a wrong one —
        # the developer has moved on and the ghost text now describes the past.
        unique = [p for p in unique if p not in SLOW_START]
        if not unique:
            return []

    preferred = _PREFERENCE[kind]
    ranked = [p for p in preferred if p in unique]
    # Anything we have no opinion about still runs, after the ones we do. A
    # provider we have not thought about is not a provider we have judged.
    rest = [p for p in unique if p not in preferred]
    return ranked + rest


def is_slow_start(provider: str) -> bool:
    return str(provider or "").strip().lower() in SLOW_START


def explain(task: str, chain: Sequence[str]) -> str:
    """One sentence for the panel: what ran this, and why that one.

    The product's argument is that you can see what it did. A routing decision
    the developer cannot read is the opaque-cost problem again in a new place.
    """
    if not chain:
        if task == INSTANT:
            return (
                "No provider fast enough for inline completion — the ones "
                "connected start too slowly to be useful at typing speed."
            )
        return "No provider is connected."
    lead = chain[0]
    if task == DEEP and is_slow_start(lead):
        return f"{lead} first — the strongest thing connected, and you already pay for it."
    if task == DEEP:
        return f"{lead} first — the strongest of the providers connected."
    if task == INSTANT:
        return f"{lead} first — fastest of the providers connected."
    return f"{lead} first, then {len(chain) - 1} more if it cannot answer."
