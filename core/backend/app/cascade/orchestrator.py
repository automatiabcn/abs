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


def _resolve_owner_key(
    provider: str,
    *,
    tenant_id: str,
    project_slug: Optional[str],
    user_subject: Optional[str],
) -> Optional[str]:
    """MT Phase 1 — per-owner (project→user→org) key override. DB-only
    (include_global=False): a missing DB key returns None so the adapter falls
    back to its global ``settings`` key exactly as before. Never raises."""
    if not (project_slug or user_subject):
        return None
    try:
        from app.multitenant.provider_keys import resolve_provider_key

        return resolve_provider_key(
            provider,
            tenant_slug=tenant_id,
            project_slug=project_slug,
            user_subject=user_subject,
            include_global=False,
        )
    except Exception as exc:  # pragma: no cover — never block a call on this
        logger.debug("per-owner key resolve skipped for %s: %s", provider, exc)
        return None


async def call_with_cascade(
    prompt: str,
    *,
    primary: str,
    model: Optional[str] = None,
    fallbacks: Sequence[str] = (),
    use_cache: bool = True,
    tenant_id: str = "_global",
    project_slug: Optional[str] = None,
    user_subject: Optional[str] = None,
    **kwargs,
) -> ProviderResponse:
    """Primary provider → fallback zinciri ile çağır.

    - Cache kontrolü (5dk TTL, tenant-scoped — UAT-016)
    - Her provider için CircuitBreaker.allow() (tenant-scoped)
    - ProviderError transient=True ise sıradaki fallback
    - transient=False → direkt raise
    - MT Phase 1: ``project_slug``/``user_subject`` verilirse provider başına
      per-owner key (DB) çözümlenir ve adapter'a ``api_key`` olarak geçilir;
      yoksa global ``settings`` key'i kullanılır (geriye dönük uyumlu).
    """
    # MT Phase 1 (W3): when no explicit caller context was passed, fall back to
    # the MCP request context (set by the transport auth from the bearer token)
    # so per-owner keys (BYOK) apply to delegated MCP tool calls too. Explicit
    # callers (panel chat / cascade route) always win.
    if tenant_id == "_global" and project_slug is None and user_subject is None:
        try:
            from app.mcp.context import get_mcp_caller

            _mt, _mu = get_mcp_caller()
            if _mt != "_global" or _mu:
                tenant_id, user_subject = _mt, _mu
        except Exception:  # pragma: no cover — MCP context is optional
            pass

    chain: List[str] = [primary, *fallbacks]
    # MT Phase 1: when a per-owner key may be used, namespace the cache by the
    # owner so one owner's BYOK answer is never served to another in the tenant.
    owner = f"p:{project_slug}" if project_slug else (f"u:{user_subject}" if user_subject else "")
    cache_key = prompt_hash(prompt, model or "", tenant_id=tenant_id, owner=owner)

    if use_cache:
        cached = await default_cache.get(cache_key)
        if cached is not None:
            cached_copy = cached.model_copy(update={"cached": True})
            return cached_copy

    last_err: Optional[Exception] = None
    # Whether anything that failed might succeed on a retry. If nothing did —
    # every provider was misconfigured or rejected the key — then telling the
    # caller "try again in 60 seconds" is a lie, and callers that handle a bad
    # key gracefully (the MCP tools) need the ProviderError itself, not a 503.
    saw_transient = False
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
        call_kwargs = kwargs
        owner_key = _resolve_owner_key(
            name,
            tenant_id=tenant_id,
            project_slug=project_slug,
            user_subject=user_subject,
        )
        if owner_key:
            call_kwargs = {**kwargs, "api_key": owner_key}
        try:
            resp = await provider.call(prompt, model=model, **call_kwargs)
            await default_breaker.record_success(breaker_id)
            if use_cache:
                await default_cache.set(cache_key, resp)
            return resp
        except ProviderError as exc:
            last_err = exc
            saw_transient = saw_transient or exc.transient
            await default_breaker.record_failure(breaker_id)
            # A permanent error means *this provider* cannot serve the request —
            # a bad key, a model it doesn't have, an account id that routes
            # nowhere. It does not mean nobody can. Raising here made one
            # misconfigured provider an outage for the whole cascade: an install
            # with a working Groq key and a half-filled Cloudflare section had no
            # assistant at all, because Cloudflare came first in the chain and
            # its 404 aborted the run before Groq was ever tried.
            #
            # So we keep going, and if every provider fails the loop still ends
            # in the structured 503 below, carrying the last error with it.
            logger.info(
                "provider %s failed (%s), trying the next one: %s",
                name,
                "transient" if exc.transient else "permanent",
                exc,
            )
            continue
        except _TRANSIENT_INFRA_EXCEPTIONS as exc:
            # Sprint 2I UAT-014 — ConnectionError / TimeoutError /
            # httpx.HTTPError used to bypass the cascade and raise 500.
            # Treat them like a transient ProviderError so the next
            # provider gets a chance.
            last_err = exc
            saw_transient = True
            await default_breaker.record_failure(breaker_id)
            logger.info(
                "provider %s infra transient (%s), sıradakine geç: %s",
                name,
                type(exc).__name__,
                exc,
            )
            continue

    # Every provider failed, and *how* they failed decides what the caller hears.
    #
    # Nothing transient in the pile means nothing here is going to get better in
    # sixty seconds: the keys are missing or wrong. Hand back the provider's own
    # error, which says so in words, and which the callers that degrade
    # gracefully on a missing key already know how to catch.
    if last_err is not None and not saw_transient and isinstance(last_err, ProviderError):
        raise last_err

    # Otherwise something was temporarily down or rate-limited, and retrying is
    # honest advice. Sprint 2I UAT-044 — a structured 503 rather than a leaked
    # stack trace.
    detail = {
        "error": "providers_unavailable",
        "providers_tried": tried,
        "retry_after": 60,
    }
    if last_err is not None:
        detail["last_error_class"] = type(last_err).__name__
        # The class name alone ("ProviderError") tells an operator nothing about
        # which half of their configuration is wrong. The message does.
        detail["last_error"] = str(last_err)[:300]
    raise HTTPException(
        status_code=503,
        detail=detail,
        headers={"Retry-After": "60"},
    )
