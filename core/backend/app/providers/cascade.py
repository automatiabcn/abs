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
from typing import Iterable, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


# Cascade order matches the customer-facing brief: paid first, then free
# providers in approximate quality order. `provider_id` aligns with the
# names used in `quota_monitor.QUOTAS` and `usage_log.append`.
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

# Back-compat alias — modules + tests still import `PROVIDER_ORDER`.
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


def is_configured(provider: str) -> bool:
    """Whether the operator has supplied a usable API key for `provider`."""
    attr = SETTINGS_KEY_ATTR.get(provider)
    if attr is None:
        return False
    value = getattr(settings, attr, "") or ""
    if not isinstance(value, str):
        return False
    if value.strip().startswith(("dev-", "REPLACE_", "TODO", "")):
        # Common placeholder strings shipped in .env.example. Empty string
        # falls through here too.
        return len(value.strip()) > _MIN_KEY_LENGTH
    return len(value.strip()) > _MIN_KEY_LENGTH


def get_active_providers(
    prefer: Optional[str] = None,
    skip_paid: bool = False,
) -> List[str]:
    """Return the ordered cascade chain of *configured* providers.
    Empty list = no providers at all (caller should 503).

    `prefer`, when supplied and configured, moves that provider to the front
    of the chain. `skip_paid=True` swaps to the free-first chain and drops
    paid providers entirely (founder-test Round 3 BUG-7 + BUG-8).
    """
    base_order = PROVIDER_ORDER_FREE_FIRST if skip_paid else PROVIDER_ORDER_PAID_FIRST
    active = [p for p in base_order if is_configured(p)]
    if skip_paid:
        active = [p for p in active if p not in PAID_PROVIDERS]
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
