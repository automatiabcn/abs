"""Cascade orchestrator — cache → breaker → provider fallback zinciri."""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from app.providers.registry import get_provider
from app.providers.schemas import ProviderError, ProviderResponse

from .breaker import default_breaker
from .cache import default_cache, prompt_hash

logger = logging.getLogger(__name__)


async def call_with_cascade(
    prompt: str,
    *,
    primary: str,
    model: Optional[str] = None,
    fallbacks: Sequence[str] = (),
    use_cache: bool = True,
    **kwargs,
) -> ProviderResponse:
    """Primary provider → fallback zinciri ile çağır.

    - Cache kontrolü (5dk TTL)
    - Her provider için CircuitBreaker.allow()
    - ProviderError transient=True ise sıradaki fallback
    - transient=False → direkt raise
    """
    chain: List[str] = [primary, *fallbacks]
    cache_key = prompt_hash(prompt, model or "")

    if use_cache:
        cached = await default_cache.get(cache_key)
        if cached is not None:
            cached_copy = cached.model_copy(update={"cached": True})
            return cached_copy

    last_err: Optional[ProviderError] = None
    for name in chain:
        if not await default_breaker.allow(name):
            logger.info("breaker open, provider atlandı: %s", name)
            continue
        try:
            provider = get_provider(name)
        except KeyError:
            logger.warning("bilinmeyen provider: %s", name)
            continue
        try:
            resp = await provider.call(prompt, model=model, **kwargs)
            await default_breaker.record_success(name)
            if use_cache:
                await default_cache.set(cache_key, resp)
            return resp
        except ProviderError as exc:
            last_err = exc
            await default_breaker.record_failure(name)
            if not exc.transient:
                raise
            logger.info("provider %s transient fail, sıradakine geç: %s", name, exc)
            continue

    if last_err is not None:
        raise last_err
    raise ProviderError("cascade: hiçbir provider çalışmadı", provider=primary, transient=True)
