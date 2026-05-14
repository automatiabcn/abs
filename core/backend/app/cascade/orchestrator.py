# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Cascade orchestrator — cache → breaker → provider fallback zinciri."""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from app.providers.registry import get_provider
from app.providers.schemas import ProviderError, ProviderResponse

from .breaker import default_breaker
from .cache import default_cache, prompt_hash

logger = logging.getLogger(__name__)


def _breaker_key(tenant_id: str, provider: str) -> str:
    """Sprint 2I UAT-016 — tenant-scoped breaker key.

    Tenant A tripping a provider must not block tenant B from using
    the same provider. ``"_global"`` keeps the legacy single-namespace
    behaviour for internal warmup paths that do not carry tenant
    context.
    """
    return f"{tenant_id}|{provider}"


async def call_with_cascade(
    prompt: str,
    *,
    primary: str,
    model: Optional[str] = None,
    fallbacks: Sequence[str] = (),
    use_cache: bool = True,
    tenant_id: str = "_global",
    **kwargs,
) -> ProviderResponse:
    """Primary provider → fallback zinciri ile çağır.

    - Cache kontrolü (5dk TTL, tenant-scoped — UAT-016)
    - Her provider için CircuitBreaker.allow() (tenant-scoped)
    - ProviderError transient=True ise sıradaki fallback
    - transient=False → direkt raise
    """
    chain: List[str] = [primary, *fallbacks]
    cache_key = prompt_hash(prompt, model or "", tenant_id=tenant_id)

    if use_cache:
        cached = await default_cache.get(cache_key)
        if cached is not None:
            cached_copy = cached.model_copy(update={"cached": True})
            return cached_copy

    last_err: Optional[ProviderError] = None
    for name in chain:
        breaker_id = _breaker_key(tenant_id, name)
        if not await default_breaker.allow(breaker_id):
            logger.info("breaker open, provider atlandı: %s", breaker_id)
            continue
        try:
            provider = get_provider(name)
        except KeyError:
            logger.warning("bilinmeyen provider: %s", name)
            continue
        try:
            resp = await provider.call(prompt, model=model, **kwargs)
            await default_breaker.record_success(breaker_id)
            if use_cache:
                await default_cache.set(cache_key, resp)
            return resp
        except ProviderError as exc:
            last_err = exc
            await default_breaker.record_failure(breaker_id)
            if not exc.transient:
                raise
            logger.info("provider %s transient fail, sıradakine geç: %s", name, exc)
            continue

    if last_err is not None:
        raise last_err
    raise ProviderError("cascade: hiçbir provider çalışmadı", provider=primary, transient=True)
