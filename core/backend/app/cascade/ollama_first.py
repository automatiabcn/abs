# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Ollama-first cascade chain.

Priority order: local Ollama (cost = $0) → Groq (cloud fast, $0 free quota)
→ Anthropic (cloud quality, paid). The standard `call_with_cascade` already
fails-through on `ProviderError(transient=True)`; OllamaProvider raises that
shape on connect-error or timeout, so the chain Just Works.

This module exposes one function:

    await call_ollama_first(prompt, model_overrides=None)

Configuration knobs (`app.config.settings`):

- `ollama_first_enabled: bool` — default False. When False, this function
  raises `RuntimeError`; callers should fall back to a different chain.
- `ollama_first_health_timeout_s: float` — default 1.5. Wraps the Ollama call
  in `asyncio.wait_for(...)`; on timeout we raise `ProviderError(transient=True)`
  so the cascade hops to the next provider.
- `ollama_url: str` — required if `ollama_first_enabled=True`.

LangFuse wiring: each provider already records `tokens_in/out` and we set
`cost_usd=0` for Ollama via the `cost_per_1k_tokens` table consumed by the
observability layer (no change needed — provider name is the lookup key).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Mapping, Optional, Sequence

from app.config import settings
from app.providers.schemas import ProviderError, ProviderResponse

from .orchestrator import call_with_cascade

logger = logging.getLogger(__name__)

DEFAULT_CHAIN: Sequence[str] = ("ollama", "groq", "anthropic")
DEFAULT_HEALTH_TIMEOUT_S = 1.5

DEFAULT_MODELS: Mapping[str, str] = {
    "ollama": "phi4",
    "groq": "llama-3.3-70b-versatile",
    "anthropic": "claude-haiku-4-5-20251001",
}


async def _call_with_health_timeout(
    prompt: str,
    *,
    primary: str,
    fallbacks: Sequence[str],
    models: Mapping[str, str],
    timeout_s: float,
) -> ProviderResponse:
    """Wrap the cascade call so a hung Ollama doesn't stall the whole request.

    Strategy:
    1. Race the Ollama call against `timeout_s`.
    2. On timeout, surface a `ProviderError(transient=True)` so the cascade
       drops Ollama and tries the next provider (Groq).
    3. Provider-internal timeouts (httpx) already raise the right shape; we
       only protect against an Ollama process that *accepts* the connection
       but never responds.
    """

    async def _ollama_then_fallback() -> ProviderResponse:
        try:
            return await asyncio.wait_for(
                call_with_cascade(
                    prompt,
                    primary=primary,
                    model=models.get(primary),
                    fallbacks=(),
                    use_cache=False,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as exc:
            logger.info(
                "ollama_first health timeout (%.1fs) — hopping to fallbacks",
                timeout_s,
            )
            raise ProviderError(
                f"ollama health timeout {timeout_s}s",
                provider=primary,
                transient=True,
            ) from exc

    try:
        return await _ollama_then_fallback()
    except ProviderError as exc:
        if not exc.transient:
            raise
        # Fall through to the cloud chain.
        for name in fallbacks:
            try:
                return await call_with_cascade(
                    prompt,
                    primary=name,
                    model=models.get(name),
                    fallbacks=(),
                    use_cache=True,
                )
            except ProviderError as inner:
                if not inner.transient:
                    raise
                continue
        raise


async def call_ollama_first(
    prompt: str,
    *,
    chain: Optional[Sequence[str]] = None,
    models: Optional[Mapping[str, str]] = None,
) -> ProviderResponse:
    """Public entry point. Raises `RuntimeError` when feature flag off."""
    if not getattr(settings, "ollama_first_enabled", False):
        raise RuntimeError(
            "ollama_first_enabled=false (set ABS_OLLAMA_FIRST_ENABLED=true to use)"
        )
    chain = tuple(chain) if chain is not None else tuple(DEFAULT_CHAIN)
    if not chain:
        raise ValueError("ollama_first chain must contain at least one provider")
    primary, *fallbacks = chain
    timeout_s = float(
        getattr(settings, "ollama_first_health_timeout_s", DEFAULT_HEALTH_TIMEOUT_S)
    )
    effective_models: Mapping[str, str] = dict(DEFAULT_MODELS)
    if models:
        effective_models = {**effective_models, **models}
    return await _call_with_health_timeout(
        prompt,
        primary=primary,
        fallbacks=fallbacks,
        models=effective_models,
        timeout_s=timeout_s,
    )
