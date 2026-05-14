# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Cascade orchestrator — cache → breaker → provider fallback zinciri."""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Sequence

import httpx
from fastapi import HTTPException

from app.providers.registry import get_provider
from app.providers.schemas import ProviderError, ProviderResponse

from .breaker import default_breaker
from .cache import default_cache, prompt_hash

logger = logging.getLogger(__name__)


# Sprint 2I UAT-014 — transient infra failures (network, timeout) used
# to bypass the cascade fallback. We catch them alongside ProviderError
# and treat them as ``transient=True``.
_TRANSIENT_INFRA_EXCEPTIONS = (
    ConnectionError,
    asyncio.TimeoutError,
    TimeoutError,
    httpx.HTTPError,
)


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

    last_err: Optional[Exception] = None
    tried: List[str] = []
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
        tried.append(name)
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
        except _TRANSIENT_INFRA_EXCEPTIONS as exc:
            # Sprint 2I UAT-014 — ConnectionError / TimeoutError /
            # httpx.HTTPError used to bypass the cascade and raise 500.
            # Treat them like a transient ProviderError so the next
            # provider gets a chance.
            last_err = exc
            await default_breaker.record_failure(breaker_id)
            logger.info(
                "provider %s infra transient (%s), sıradakine geç: %s",
                name,
                type(exc).__name__,
                exc,
            )
            continue

    # Sprint 2I UAT-044 — every provider failed: surface a structured
    # 503 instead of leaking the last exception's stack trace to the
    # client. ``Retry-After`` advises the caller to back off.
    detail = {
        "error": "providers_unavailable",
        "providers_tried": tried,
        "retry_after": 60,
    }
    if last_err is not None:
        detail["last_error_class"] = type(last_err).__name__
    raise HTTPException(
        status_code=503,
        detail=detail,
        headers={"Retry-After": "60"},
    )
