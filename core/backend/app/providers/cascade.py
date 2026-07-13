# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Phase 11 / Q3 — Cascade orchestrator with provider degradation matrix.

Customer scenario: operator boots ABS with anywhere from 0 to 6 provider
keys configured. The cascade must:

* Skip un-configured providers (empty / placeholder API keys).
* Order remaining providers by preference, falling through on rate-limit /
  timeout / 5xx errors.
* Surface a clean 503 when zero providers are usable so the UI can show a
  "configure at least one key" CTA.

This module is also the single source of truth that `quota.py` consults to
mark each provider's `configured: bool` slice — the panel uses that flag to
gray out un-configured rows instead of pretending they're idle.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


# Explicit quality-first chain (Anthropic first). NOT the runtime default —
# kept for callers that deliberately opt into paid-first ordering. The default
# cascade is `PROVIDER_ORDER_DEFAULT` (free-first), see below. `provider_id`
# aligns with the names used in `quota_monitor.QUOTAS` and `usage_log.append`.
PROVIDER_ORDER_PAID_FIRST: tuple[str, ...] = (
    "anthropic",
    "groq",
    "cerebras",
    "gemini",
    "cloudflare",
    "cohere",
)

# Cost-saving chain — used when the request opts out of paid providers
# (`skip_paid_providers=true` or wizard's free-tier path). `groq` leads
# because Llama 3.3 70B + GPT-OSS 120B give the best free-tier quality
# and lowest p95.
PROVIDER_ORDER_FREE_FIRST: tuple[str, ...] = (
    "groq",
    "cerebras",
    "gemini",
    "cohere",
    "cloudflare",
)

# Default cascade chain — free providers first, paid Anthropic appended as the
# last-resort premium fallback. This is the authoritative behaviour from
# `docs/ABS_HYBRID_TIER_PROMISE.md` (ABS engineering sign-off):
# "Free path first … cascade … none of those paths touch Anthropic … 95%+ of
# the work on free providers." Anthropic stays reachable as the quota-protected
# premium lane (quota_monitor warns @80%, hard-blocks @95% → falls to Groq) so
# quality is preserved while the default keeps spend at $0. Callers opt into
# Claude per-request via `prefer="anthropic"`, explicit model, or a pipeline.
PROVIDER_ORDER_DEFAULT: tuple[str, ...] = (
    *PROVIDER_ORDER_FREE_FIRST,
    "anthropic",
)

# Back-compat alias — modules + tests still import `PROVIDER_ORDER`. Points at
# the explicit paid-first chain for callers that want quality-first ordering on
# purpose; the runtime DEFAULT is `PROVIDER_ORDER_DEFAULT` (free-first).
PROVIDER_ORDER: tuple[str, ...] = PROVIDER_ORDER_PAID_FIRST

# Providers that cost money per token. `skip_paid_providers=true` filters
# these out of the active chain. Future paid providers (OpenAI etc.)
# get added here, not to the public chain.
PAID_PROVIDERS: frozenset[str] = frozenset({"anthropic"})


# Settings attribute name per provider — Cloudflare uses `cf_api_token` not
# `cloudflare_api_key`, so we keep an explicit map rather than f-stringing.
SETTINGS_KEY_ATTR: dict[str, str] = {
    "anthropic": "anthropic_api_key",
    "groq": "groq_api_key",
    "cerebras": "cerebras_api_key",
    "gemini": "gemini_api_key",
    "cloudflare": "cf_api_token",
    "cohere": "cohere_api_key",
}


# Plausibility threshold — most provider keys are 32+ chars; allow demo
# overrides of 9+ so smoke fixtures can flip a key on without using a real
# secret.
_MIN_KEY_LENGTH = 8


# The strings .env.example ships. They are long enough to pass a length check
# and they are not keys, and a provider "configured" with one of them joins the
# cascade, fails every call, and takes the chain down with it. The old check had
# two identical branches and so accepted them all.
_PLACEHOLDER_MARKERS = (
    "replace-with",
    "replace_with",
    "replace_me",
    "changeme",
    "change-me",
    "your-key",
    "your_key",
    "todo",
    "xxxxxxxx",
)


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _has_real_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return len(stripped) > _MIN_KEY_LENGTH and not _is_placeholder(stripped)


def is_configured(provider: str) -> bool:
    """Whether the operator has supplied a usable API key for `provider`.

    "Usable" is doing real work here. A provider that is *half* configured — a
    Cloudflare token with the sample account id still in place — is worse than
    one that is absent: it sits in the chain, 404s on every call, and (before
    the orchestrator learned to keep going) aborted the whole cascade, so an
    install with a perfectly good Groq key had no working assistant at all.
    """
    attr = SETTINGS_KEY_ATTR.get(provider)
    if attr is None:
        return False
    if not _has_real_value(getattr(settings, attr, "")):
        return False
    # Cloudflare needs two halves. The token alone routes nowhere.
    if provider == "cloudflare" and not _has_real_value(
        getattr(settings, "cf_account_id", "")
    ):
        return False
    return True


def get_active_providers(
    prefer: Optional[str] = None,
    skip_paid: bool = False,
    extra_configured: frozenset[str] = frozenset(),
) -> List[str]:
    """Return the ordered cascade chain of *configured* providers.
    Empty list = no providers at all (caller should 503).

    Default ordering is free-first with Anthropic as the last-resort premium
    fallback (`PROVIDER_ORDER_DEFAULT`, per ABS_HYBRID_TIER_PROMISE). `prefer`,
    when supplied and configured, moves that provider to the front of the chain.
    `skip_paid=True` swaps to the free-only chain and drops paid providers
    entirely.

    `extra_configured` is the set of providers this caller has supplied their own
    key for (BYOK), at any tier — project, user, or org. Two things follow, and
    the second one is the point:

    It *activates* a provider the operator never configured globally, so someone
    can bring a provider the server has never heard of.

    And it *promotes* it. Free-first exists to keep the operator's bill at zero,
    which is exactly right for the operator's own keys — but a person who pastes
    in their own Anthropic key and is then answered by the free tier has bought
    nothing. Pasting a key is a statement of preference, so the providers a
    caller owns go to the front, in their usual relative order, and everything
    the operator configured follows behind as the fallback it was always meant to
    be. A caller who brings nothing sees the free chain, untouched.
    """
    base_order = PROVIDER_ORDER_FREE_FIRST if skip_paid else PROVIDER_ORDER_DEFAULT
    active = [p for p in base_order if is_configured(p) or p in extra_configured]
    if skip_paid:
        # An explicit "free only" wins over whose money it is: someone asking to
        # stay on the free tier means it, key or no key.
        active = [p for p in active if p not in PAID_PROVIDERS]

    owned = [p for p in active if p in extra_configured]
    if owned:
        active = owned + [p for p in active if p not in extra_configured]

    if prefer and prefer in active:
        active.remove(prefer)
        active.insert(0, prefer)
    return active


def configured_map() -> dict[str, bool]:
    """`{provider: bool}` — used by /v1/system/quota_status to mark slices."""
    return {p: is_configured(p) for p in PROVIDER_ORDER}


def order_by_preference(
    providers: Iterable[str], prefer: Optional[str]
) -> List[str]:
    """Public helper — re-uses `get_active_providers` ordering on a custom
    subset. Mainly for tests that want to verify ordering without touching
    settings."""
    base = list(providers)
    if prefer and prefer in base:
        base.remove(prefer)
        base.insert(0, prefer)
    return base
