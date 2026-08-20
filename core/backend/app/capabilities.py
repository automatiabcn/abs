# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""What this install can actually do, given the keys it has.

ABS runs on the developer's own keys, so a fresh install is not "broken" or
"working" — it is somewhere on a slope. One free key already buys inline edits,
graded proposals and a knowledge base; a second buys failover and second
opinions, because neither means anything with one provider to ask.

The product has always known which providers are configured. What it could not
say was the sentence a person actually needs: **what works right now, what does
not, and which single key would change that.** Without it a new install is a
guessing game — the panel says "1 provider ready" and the reader has to infer
what that costs them.

Two rules this module is built to:

* A capability is available only when it would really run. RAG with no
  embedding source silently falls back to hashes of the text: five chunks come
  back, the model answers from them, and none of them relate to the question.
  That is reported as unavailable, because a wrong answer delivered confidently
  is worse than a missing feature.
* Every unavailable capability names the cheapest real way to get it. Telling
  someone a feature needs "an embedding provider" is not help; telling them
  Ollama is a free local install, or that Cohere has a free tier, is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

# Providers that can answer a chat/completion request. `cohere` IS here: it
# sits in the cascade order and answers chat (command-r-plus took a live
# question on 2026-08-18) besides embedding and reranking, so leaving it out
# under-counted the failovers a Cohere key really buys.
CHAT_PROVIDERS = frozenset(
    {"groq", "cerebras", "gemini", "anthropic", "cloudflare", "openrouter", "cohere", "ollama", "mlx"}
)

# The Senior Judge is pinned to gpt-oss-120b for comparable scores, and only
# these providers serve it (app/judge/senior.py _JUDGE_ROUTES). A gemini-only
# install has "a chat provider" and no judge — the panel said otherwise until
# 2026-08-18, and every score came back None.
JUDGE_PROVIDERS = frozenset({"groq", "cerebras"})

# Embedding sources, in the order `embedding_backend="auto"` resolves them.
# `mock` is not here on purpose — see the module docstring.
EMBEDDING_SOURCES = frozenset({"ollama", "sentence_transformers", "cohere", "onnx_cuda", "onnx_cpu"})

# Where a key actually comes from, in the words someone can act on. Free tiers
# first, because the product's default routing prefers them and because the
# cheapest way to unlock a capability should be the one we name.
HOW_TO_GET = {
    "groq": "Free tier — console.groq.com/keys, no card.",
    "cerebras": "Free tier — cloud.cerebras.ai, no card.",
    "gemini": "Free tier — aistudio.google.com/apikey, no card.",
    "cloudflare": "Free tier — dash.cloudflare.com → Workers AI.",
    "cohere": "Free trial key — dashboard.cohere.com/api-keys.",
    "anthropic": "Paid — console.anthropic.com.",
    "openrouter": "Paid, many models behind one key — openrouter.ai/keys.",
    "ollama": "Free and local — ollama.com, then `ollama pull bge-m3`.",
    "mlx": "Free and local, Apple silicon only.",
}

FREE_TO_START = frozenset({"groq", "cerebras", "gemini", "cloudflare", "ollama", "mlx", "cohere"})


@dataclass(frozen=True)
class Capability:
    """One thing the product offers, and what it costs to have it."""

    key: str
    title: str
    # Why a reader should care. Not a feature name — what they get.
    promise: str
    # How many distinct chat providers it needs. 0 = runs locally.
    needs_chat_providers: int = 0
    # True when it needs a real embedding source.
    needs_embeddings: bool = False
    # When set, at least one of THESE providers must be usable (the judge's
    # pinned model is served by two providers, not by "any chat provider").
    needs_any_of: frozenset = frozenset()
    # True when it needs an OS sandbox mechanism on this machine.
    needs_sandbox: bool = False


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        key="ask",
        title="Ask about your code",
        promise="Questions answered about the file you have open, with the provider and cost named.",
        needs_chat_providers=1,
    ),
    Capability(
        key="edit",
        title="Graded edits",
        promise="Inline edits and Composer proposals, each scored before you approve it.",
        needs_chat_providers=1,
    ),
    Capability(
        key="judge",
        title="Senior judge",
        promise="Every proposed change reviewed and scored, with the reasoning shown.",
        needs_chat_providers=1,
        needs_any_of=JUDGE_PROVIDERS,
    ),
    Capability(
        key="failover",
        title="Failover between providers",
        promise="When one provider is down, rate-limited or slow, the next one answers.",
        # One provider cannot fail over to itself. This is the capability a
        # second key buys, and the reason to bring one.
        needs_chat_providers=2,
    ),
    Capability(
        key="second_opinion",
        title="Second opinion",
        promise="The same question asked of independent providers, so you can see where they disagree.",
        needs_chat_providers=2,
    ),
    Capability(
        key="knowledge",
        title="Knowledge base",
        promise="Your workspace indexed and searchable, with the matching lines and their scores.",
        needs_embeddings=True,
    ),
    Capability(
        key="blast_radius",
        title="Blast radius",
        promise="What else refers to the thing you are changing, before you change it.",
    ),
    Capability(
        key="checks",
        title="Sandboxed checks",
        promise="Your tests run in the OS's own sandbox, and ABS says so when it could not.",
        needs_sandbox=True,
    ),
)


@dataclass
class CapabilityState:
    capability: Capability
    available: bool
    # Why not, in a sentence the reader can act on. Empty when available.
    blocked_by: str = ""
    # The cheapest keys that would unlock it, best first.
    unlock_with: list[str] = field(default_factory=list)
    # True when at least one unlock is free to obtain.
    unlock_is_free: bool = False

    @property
    def how_to(self) -> str:
        """The one sentence that turns 'unavailable' into a next step."""
        if self.available or not self.unlock_with:
            return ""
        return HOW_TO_GET.get(self.unlock_with[0], "")


def _chat_providers(configured: Iterable[str]) -> list[str]:
    return sorted({p.strip().lower() for p in configured if p} & CHAT_PROVIDERS)


def _suggest(configured: set[str], want: int) -> list[str]:
    """Which keys to bring next, free ones first, cheapest path to `want`."""
    missing = [p for p in CHAT_PROVIDERS - configured]
    free = sorted(p for p in missing if p in FREE_TO_START)
    paid = sorted(p for p in missing if p not in FREE_TO_START)
    return (free + paid)[: max(1, want)]


def assess(
    configured_providers: Iterable[str],
    *,
    embedding_backend: Optional[str] = None,
    unusable_now: Optional[dict[str, str]] = None,
    sandbox_available: Optional[bool] = None,
) -> list[CapabilityState]:
    """What works, what does not, and what one more key would change.

    `embedding_backend` is the backend that actually resolved — not what was
    requested. "auto" that fell through to "mock" is not an embedding source,
    and reporting it as one is how a knowledge base returns five confident,
    unrelated chunks.
    """
    configured = {p.strip().lower() for p in configured_providers if p}
    # A provider that is rate-limited or whose breaker is open has a key and
    # cannot answer. Counting it would promise a failover that will not happen
    # this minute; forgetting it had a key would tell the reader to go and buy
    # one they already own. It is excluded from the count AND remembered, so
    # the reason given is the true one.
    down = {k.strip().lower(): v for k, v in (unusable_now or {}).items() if k}
    usable = configured - set(down)
    chat = _chat_providers(usable)
    backend = (embedding_backend or "").strip().lower()
    has_embeddings = backend in EMBEDDING_SOURCES or "cohere" in configured or "ollama" in configured

    states: list[CapabilityState] = []
    for cap in CAPABILITIES:
        if cap.needs_sandbox and sandbox_available is False:
            # "Checks" was always on. On a machine with no seatbelt/bwrap/
            # restricted token the Run button offered a promise the runner
            # refuses (fail-closed) — the panel and the runner disagreed.
            states.append(
                CapabilityState(
                    capability=cap,
                    available=False,
                    blocked_by=(
                        "No OS sandbox on this machine (macOS seatbelt, Linux "
                        "bubblewrap, Windows restricted token), so ABS will not "
                        "run checks unconfined."
                    ),
                    unlock_with=[],
                    unlock_is_free=False,
                )
            )
            continue
        if cap.needs_any_of and not (set(chat) & cap.needs_any_of):
            resting_any = set(_chat_providers(configured)) & cap.needs_any_of
            if resting_any:
                asleep = sorted(p for p in down if p in cap.needs_any_of)
                why = "; ".join(f"{p} {down[p]}" for p in asleep) or "a provider is resting"
                states.append(
                    CapabilityState(
                        capability=cap,
                        available=False,
                        blocked_by=f"Not right now — {why}. The key is fine; this passes.",
                        unlock_with=[],
                        unlock_is_free=False,
                    )
                )
                continue
            wanted = sorted(cap.needs_any_of, key=lambda p: (p not in FREE_TO_START, p))
            states.append(
                CapabilityState(
                    capability=cap,
                    available=False,
                    blocked_by=(
                        f"Needs a key for one of {', '.join(wanted)} — the judge's model "
                        f"(gpt-oss-120b) is served only there, so scores stay comparable."
                    ),
                    unlock_with=wanted,
                    unlock_is_free=any(p in FREE_TO_START for p in wanted),
                )
            )
            continue
        if cap.needs_embeddings and not has_embeddings:
            states.append(
                CapabilityState(
                    capability=cap,
                    available=False,
                    blocked_by=(
                        "No embedding source, so search would match on hashes rather "
                        "than meaning — ABS will not pretend that is a knowledge base."
                    ),
                    unlock_with=["ollama", "cohere"],
                    unlock_is_free=True,
                )
            )
            continue
        if len(chat) < cap.needs_chat_providers:
            # Would this be working if nothing were throttled? Then the answer
            # is "wait", not "buy" — and saying "buy" would be advice to spend
            # money on a problem that fixes itself.
            resting = _chat_providers(configured)
            if len(resting) >= cap.needs_chat_providers:
                asleep = sorted(p for p in down if p in CHAT_PROVIDERS)
                why = "; ".join(f"{p} {down[p]}" for p in asleep) or "a provider is resting"
                states.append(
                    CapabilityState(
                        capability=cap,
                        available=False,
                        blocked_by=f"Not right now — {why}. The key is fine; this passes.",
                        unlock_with=[],
                        unlock_is_free=False,
                    )
                )
                continue
            need = cap.needs_chat_providers - len(chat)
            suggestions = _suggest(configured, need)
            states.append(
                CapabilityState(
                    capability=cap,
                    available=False,
                    blocked_by=(
                        "Needs a provider key."
                        if cap.needs_chat_providers == 1
                        else f"Needs {cap.needs_chat_providers} providers to compare or fall back between; "
                        f"there {'is' if len(chat) == 1 else 'are'} {len(chat)}."
                    ),
                    unlock_with=suggestions,
                    unlock_is_free=any(s in FREE_TO_START for s in suggestions),
                )
            )
            continue
        states.append(CapabilityState(capability=cap, available=True))
    return states


def summarise(states: Iterable[CapabilityState]) -> dict:
    """The shape a panel renders: counts, and the single best next step."""
    states = list(states)
    ready = [s for s in states if s.available]
    blocked = [s for s in states if not s.available]
    # The most useful next key is the one that unlocks the most, free first.
    tally: dict[str, int] = {}
    for s in blocked:
        for p in s.unlock_with[:1]:
            tally[p] = tally.get(p, 0) + 1
    next_key = ""
    if tally:
        next_key = sorted(
            tally, key=lambda p: (-tally[p], p not in FREE_TO_START, p)
        )[0]
    return {
        "ready": len(ready),
        "total": len(states),
        "blocked": [s.capability.key for s in blocked],
        "next_key": next_key,
        "next_key_is_free": next_key in FREE_TO_START,
        "next_key_how": HOW_TO_GET.get(next_key, ""),
        "next_key_unlocks": sorted(
            s.capability.key for s in blocked if s.unlock_with[:1] == [next_key]
        ),
    }


# --- when a resting provider comes back --------------------------------------


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def rest_reason(code: str, *, minutes_to_utc_midnight: int) -> str:
    """Turn the meter's machine reason into when the provider comes back.

    A quota that has run out is not a missing key, and the useful sentence is
    not "buy another one" — it is **when this one renews**. Daily allowances
    reset at UTC midnight; a per-minute limit clears while you read this; a 429
    cooldown says how long it has left. Telling somebody to spend money on a
    limit that lifts tonight is the wrong advice twice over.
    """
    c = (code or "").strip().lower()
    if c.startswith("cooldown_"):
        secs = "".join(ch for ch in c[len("cooldown_"):] if ch.isdigit())
        if secs and int(secs) > 0:
            n = int(secs)
            return (
                f"is backing off after a rate limit; about {_plural(n, 'second')} left"
                if n < 90
                else f"is backing off after a rate limit; about {_plural(round(n / 60), 'minute')} left"
            )
        return "is backing off after a rate limit"
    if c.startswith("rpm_full"):
        return "hit its per-minute limit; it clears within a minute"
    if c.startswith(("rpd_exhausted", "tpd_exhausted", "neurons_exhausted")):
        m = max(0, int(minutes_to_utc_midnight))
        hours, mins = divmod(m, 60)
        when = (
            f"in {_plural(hours, 'hour')}"
            if hours and not mins
            else f"in {_plural(hours, 'hour')} {_plural(mins, 'minute')}"
            if hours
            else f"in {_plural(mins, 'minute')}"
        )
        return f"has used today's allowance; it renews at midnight UTC, {when}"
    if c.startswith("breaker"):
        return "has tripped its breaker after repeated failures; it retries by itself"
    return "cannot answer right now"


def minutes_to_utc_midnight(now) -> int:
    """Whole minutes until the daily counters reset."""
    return int(((24 - now.hour) * 60) - now.minute) % (24 * 60) or 24 * 60
