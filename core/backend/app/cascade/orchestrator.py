# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Cascade orchestrator — cache, then circuit breaker, then provider fallback."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Dict, List, Mapping, Optional, Sequence

import httpx

from app.providers.registry import get_provider
from app.providers.schemas import (
    CascadeUnavailable,
    ProviderError,
    ProviderResponse,
)

from . import provider_health as _health
from .breaker import default_breaker
from .cache import default_cache, prompt_hash

logger = logging.getLogger(__name__)


# Infra failures (network, timeout) are caught alongside ProviderError and
# treated as transient — otherwise they would escape the cascade and no
# fallback would ever run.
_TRANSIENT_INFRA_EXCEPTIONS = (
    ConnectionError,
    asyncio.TimeoutError,
    TimeoutError,
    httpx.HTTPError,
)


def _breaker_key(tenant_id: str, provider: str) -> str:
    """Tenant-scoped breaker key.

    One tenant tripping a provider must not open the breaker for every other
    tenant. Callers with no tenant context (internal warmup) pass ``"_global"``
    and share a single namespace.
    """
    return f"{tenant_id}|{provider}"


def _resolve_owner_key(
    provider: str,
    *,
    tenant_id: str,
    project_slug: Optional[str],
    user_subject: Optional[str],
) -> Optional[str]:
    """Per-owner (project → user → org) key override, from the DB only.

    Returns None when no owner key exists, which leaves the adapter on its
    global ``settings`` key. Never raises — a key lookup must not fail a call.
    """
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


def _meter(resp: ProviderResponse, *, provider: str, tenant_id: str) -> None:
    """Record one answered request against the tenant's usage.

    It is recorded *here*, at the one place every answer passes through, rather
    than at each caller. Metering used to live in the `/v1/cascade/run` route
    alone, so it saw API traffic and nothing else: chat — the surface the whole
    product is built around — never reached the usage page at all. A customer
    watching their free-path share, or wondering what a busy week costs, was
    reading a number that ignored almost everything they had actually done.

    Never raises. A metering failure must not lose an answer the customer has
    already been given.
    """
    try:
        from app.services import usage_log

        tokens = int(resp.tokens_in or 0) + int(resp.tokens_out or 0)
        # `_global` is the orchestrator's "no caller context" marker, not a
        # tenant. Writing it as one would file this call under a tenant nobody
        # can see, which is how usage goes missing.
        slug = (tenant_id or "").strip()
        usage_log.append(
            provider,
            tokens=tokens,
            tenant_slug="default" if slug in ("", "_global") else slug,
        )
    except Exception:  # noqa: BLE001 — metering is never worth an outage
        logger.debug("usage metering skipped", exc_info=True)


def record_direct_call(
    resp: Optional[ProviderResponse],
    *,
    provider: str,
    tenant_id: Optional[str],
    model: str = "",
    exc: Optional[Exception] = None,
) -> None:
    """Book a provider call that did NOT go through call_with_cascade.

    The judge and the second opinion call adapters directly (they pin models
    and keys the cascade would not), and until 2026-08-18 those calls were
    invisible to the usage log, the quota meter and the health readout — a
    paid second-opinion leg never reached the cost page. One helper, same
    books as the cascade. Never raises.
    """
    tenant = tenant_id or "_global"
    try:
        if exc is not None or resp is None:
            _record_quota(provider, tenant_id=tenant, status_code=500, exc=exc, model=model)
            _health.note_failure(
                provider, tenant=tenant,
                permanent=not bool(getattr(exc, "transient", True)) if exc is not None else False,
                detail=str(exc) if exc is not None else "", model=model,
            )
            return
        _meter(resp, provider=provider, tenant_id=tenant)
        _record_quota(
            provider,
            tenant_id=tenant,
            tokens=int(resp.tokens_in or 0) + int(resp.tokens_out or 0),
            status_code=200,
            model=str(resp.model or model or ""),
        )
        _health.note_success(provider, tenant=tenant, model=str(resp.model or model or ""))
    except Exception:  # noqa: BLE001 — bookkeeping never costs an answer
        pass


def _record_quota(
    provider: str,
    *,
    tenant_id: str,
    tokens: int = 0,
    status_code: int = 200,
    exc: Optional[Exception] = None,
    model: str = "",
) -> None:
    """Feed the per-tenant quota meter (Cost HUD + 429 cooldown). Never raises.

    Records only; it does not change provider selection. A rate-limit-shaped
    ProviderError is recorded as a 429 so the meter can show a cooldown.
    """
    try:
        from app.cascade import quota_meter

        sc = status_code
        if (
            exc is not None
            and getattr(exc, "transient", False)
            and quota_meter.looks_like_rate_limit(str(exc))
        ):
            sc = 429
        quota_meter.record_usage(
            provider, tenant_id=tenant_id, tokens=tokens, status_code=sc, model=model
        )
    except Exception:  # noqa: BLE001 — metering is never worth an outage
        logger.debug("quota meter skipped", exc_info=True)


def _prune_dead_legs(chain: List[str], tenant_id: str) -> List[str]:
    """Leave out providers whose last outcome was a permanent failure and
    recent — unless that would leave nothing, in which case they are all
    tried: a chain of dead legs still owes the caller a real error."""
    kept = [n for n in chain if not _health.should_skip(n, tenant=tenant_id)]
    if kept != chain:
        logger.info(
            "cascade skipping providers with a standing permanent failure: %s",
            [n for n in chain if n not in kept],
        )
    return kept or list(chain)


#: When every leg of a chain was rate-limited, the chain is tried once more
#: after this pause. A single-provider install on a free tier (the common
#: first install) turned a per-minute 429 into "every provider failed"; the
#: same key answered 200 seconds later (CI scenarios, 2026-08-28).
RATE_LIMIT_SECOND_PASS_S = 4.0


#: A provider's Retry-After is honoured up to this many seconds; beyond it the
#: caller is better served by the 503 and its own retry.
RATE_LIMIT_HINT_CAP_S = 20.0


def _retry_hint(exc: BaseException) -> float:
    """What the provider asked us to wait, capped; 0 when it said nothing."""
    wait = getattr(exc, "retry_after", None)
    try:
        return min(RATE_LIMIT_HINT_CAP_S, float(wait)) if wait else 0.0
    except (TypeError, ValueError):
        return 0.0



def _looks_generation_failure(exc: BaseException) -> bool:
    """The provider rejected the MODEL's output (Groq json_validate_failed,
    'could not be parsed'), not our request or our key."""
    text = str(exc).lower()
    return "json_validate_failed" in text or "failed_generation" in text or "could not be parsed" in text


def _looks_rate_limited(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "too many requests" in text


async def call_with_cascade(
    prompt: str,
    *,
    primary: str,
    model: Optional[str] = None,
    # A model per provider, for callers that pin one. `model` alone goes to
    # EVERY leg — harmless while it is None (each adapter uses its own
    # default) and a trap the moment somebody pins one, because the primary's
    # model then reaches providers that do not serve it and every fallback
    # 404s. That would break the thing the product leads with, the agent that
    # does not stop when a provider does, while fixing something smaller.
    models: Optional[Mapping[str, str]] = None,
    fallbacks: Sequence[str] = (),
    use_cache: bool = True,
    tenant_id: str = "_global",
    project_slug: Optional[str] = None,
    user_subject: Optional[str] = None,
    _second_pass: bool = False,
    **kwargs,
) -> ProviderResponse:
    """Call the primary provider, falling back down the chain on failure.

    The cache and the circuit breaker are both tenant-scoped. A provider that
    fails hands the request to the next one in the chain; if every provider
    fails, the failure the caller sees depends on whether any of them looked
    retryable (see below).

    When ``project_slug`` or ``user_subject`` is given, a per-owner key from the
    DB is resolved for each provider and passed to the adapter; without one the
    adapter uses the global key from ``settings``.
    """
    # With no explicit caller context, fall back to the MCP request context so
    # per-owner keys also apply to delegated MCP tool calls. An explicit caller
    # always wins.
    if tenant_id == "_global" and project_slug is None and user_subject is None:
        try:
            from app.mcp.context import get_mcp_caller

            _mt, _mu = get_mcp_caller()
            if _mt != "_global" or _mu:
                tenant_id, user_subject = _mt, _mu
        except Exception:  # pragma: no cover — MCP context is optional
            pass

    chain: List[str] = _prune_dead_legs([primary, *fallbacks], tenant_id)
    # When a per-owner key may be used, the cache is namespaced by owner so one
    # owner's answer is never served to another inside the same tenant.
    owner = (
        f"p:{project_slug}"
        if project_slug
        else (f"u:{user_subject}" if user_subject else "")
    )
    cache_key = prompt_hash(prompt, model or "", tenant_id=tenant_id, owner=owner)

    if use_cache:
        cached = await default_cache.get(cache_key)
        if cached is not None:
            # A cache hit tried no providers this time — say so honestly.
            cached_copy = cached.model_copy(
                update={"cached": True, "providers_tried": []}
            )
            return cached_copy

    last_err: Optional[Exception] = None
    # Whether anything that failed might succeed on a retry. If nothing did —
    # every provider was misconfigured or rejected the key — then telling the
    # caller "try again in 60 seconds" is a lie, and callers that handle a bad
    # key gracefully (the MCP tools) need the ProviderError itself, not a 503.
    saw_transient = False
    rate_limited = False
    generation_failed = False
    rate_limit_wait = RATE_LIMIT_SECOND_PASS_S
    tried: List[str] = []
    for name in chain:
        breaker_id = _breaker_key(tenant_id, name)
        if not await default_breaker.allow(breaker_id):
            logger.info("breaker open, provider skipped: %s", breaker_id)
            continue
        try:
            provider = get_provider(name)
        except KeyError:
            logger.warning("unknown provider: %s", name)
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
        # Each leg gets a model it actually serves; a provider we have no
        # pin for keeps its own default rather than inheriting somebody
        # else's model name.
        leg_model = (models or {}).get(name) or model
        try:
            resp = await provider.call(prompt, model=leg_model, **call_kwargs)
            # Expose the failover trail (attempts so far, winner last) on the
            # success path too — chat/Cost-HUD can show "tried A → B → C". It was
            # only surfaced on total failure via CascadeUnavailable before.
            resp.providers_tried = list(tried)
            await default_breaker.record_success(breaker_id)
            _health.note_success(name, tenant=tenant_id, model=str(resp.model or leg_model or ""))
            if use_cache:
                await default_cache.set(cache_key, resp)
            _meter(resp, provider=name, tenant_id=tenant_id)
            _record_quota(
                name,
                tenant_id=tenant_id,
                tokens=int(resp.tokens_in or 0) + int(resp.tokens_out or 0),
                status_code=200,
                model=resp.model or (model or ""),
            )
            return resp
        except ProviderError as exc:
            last_err = exc
            saw_transient = saw_transient or exc.transient
            rate_limited = rate_limited or _looks_rate_limited(exc)
            generation_failed = generation_failed or _looks_generation_failure(exc)
            rate_limit_wait = max(rate_limit_wait, _retry_hint(exc))
            await default_breaker.record_failure(breaker_id)
            # The panels read this: a PERMANENT failure (bad key, payment
            # required, retired model) is what stops "ready" from being said
            # about a provider that answers nothing (2026-08-18).
            _health.note_failure(
                name, tenant=tenant_id, permanent=not exc.transient,
                detail=str(exc), model=str(leg_model or ""),
            )
            _record_quota(name, tenant_id=tenant_id, status_code=500, exc=exc)
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
            # Network-level failures are transient by definition: treat them
            # like a transient ProviderError so the next provider gets a turn
            # instead of the request dying with a 500.
            last_err = exc
            saw_transient = True
            await default_breaker.record_failure(breaker_id)
            _health.note_failure(name, tenant=tenant_id, permanent=False, detail=str(exc))
            logger.info(
                "provider %s infra transient (%s), moving to the next one: %s",
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
    if (
        last_err is not None
        and not saw_transient
        and isinstance(last_err, ProviderError)
    ):
        raise last_err

    # Otherwise something was temporarily down or rate-limited, and retrying is
    # honest advice.
    #
    # This used to raise an HTTPException from here — a web-framework exception
    # thrown by a library that agents, MCP tools, pipelines and workers all call
    # from outside any web request. They catch ProviderError; this sailed past
    # them. `CascadeUnavailable` *is* a ProviderError, so they degrade instead of
    # dying, and the HTTP layer still answers with the same structured 503 (see
    # the handler in app/main.py).
    if saw_transient and (rate_limited or generation_failed) and not _second_pass:
        # A rejected generation (the model's JSON or tool call failed the
        # provider's own validation) is stochastic: the same request usually
        # succeeds on the next try, and with one provider in the chain there
        # is no next leg — so the chain gets one more pass right away
        # (scenarios G1/C10, 2026-08-28). A rate limit waits first.
        wait = rate_limit_wait if rate_limited else 0.0
        logger.info(
            "every provider in the chain %s; one more pass after %.1fs",
            "was rate-limited" if rate_limited else "rejected its own generation",
            wait,
        )
        await asyncio.sleep(wait)
        return await call_with_cascade(prompt, primary=primary, model=model, models=models, fallbacks=fallbacks, use_cache=use_cache, tenant_id=tenant_id, project_slug=project_slug, user_subject=user_subject, _second_pass=True, **kwargs)
    raise CascadeUnavailable(
        "every provider in the chain failed; some may recover shortly",
        providers_tried=tried,
        last_error=last_err,
    )


async def stream_with_cascade(
    prompt: str,
    *,
    primary: str,
    model: Optional[str] = None,
    models: Optional[Mapping[str, str]] = None,
    fallbacks: Sequence[str] = (),
    use_cache: bool = True,
    tenant_id: str = "_global",
    project_slug: Optional[str] = None,
    user_subject: Optional[str] = None,
    _second_pass: bool = False,
    **kwargs,
) -> AsyncIterator[Dict]:
    """`call_with_cascade`, delivered as it is produced.

    Yields dicts: ``{"type": "provider", "name"}`` when a leg starts,
    ``{"type": "delta", "text"}`` for each piece of the answer, and one
    closing ``{"type": "done", "response": ProviderResponse}``. A leg that
    fails before its first piece of text hands over to the next provider
    exactly as the blocking cascade does — the caller never sees it. A leg
    that fails after text has started cannot be retried without showing the
    developer the same answer twice, so it ends with ``{"type": "error"}``
    carrying what was said so far.

    The books are kept the same way as the blocking call: breaker, health,
    metering and quota at the one place every answer passes through, and the
    finished answer goes into the same cache so a repeat is served from it.
    """
    if tenant_id == "_global" and project_slug is None and user_subject is None:
        try:
            from app.mcp.context import get_mcp_caller

            _mt, _mu = get_mcp_caller()
            if _mt != "_global" or _mu:
                tenant_id, user_subject = _mt, _mu
        except Exception:  # pragma: no cover — MCP context is optional
            pass

    chain: List[str] = _prune_dead_legs([primary, *fallbacks], tenant_id)
    owner = (
        f"p:{project_slug}"
        if project_slug
        else (f"u:{user_subject}" if user_subject else "")
    )
    cache_key = prompt_hash(prompt, model or "", tenant_id=tenant_id, owner=owner)
    if use_cache:
        cached = await default_cache.get(cache_key)
        if cached is not None:
            cached_copy = cached.model_copy(update={"cached": True, "providers_tried": []})
            yield {"type": "provider", "name": cached_copy.provider, "cached": True}
            if cached_copy.text:
                yield {"type": "delta", "text": cached_copy.text}
            yield {"type": "done", "response": cached_copy}
            return

    last_err: Optional[Exception] = None
    saw_transient = False
    rate_limited = False
    generation_failed = False
    rate_limit_wait = RATE_LIMIT_SECOND_PASS_S
    yielded_delta = False
    tried: List[str] = []
    for name in chain:
        breaker_id = _breaker_key(tenant_id, name)
        if not await default_breaker.allow(breaker_id):
            logger.info("breaker open, provider skipped: %s", breaker_id)
            continue
        try:
            provider = get_provider(name)
        except KeyError:
            logger.warning("unknown provider: %s", name)
            continue
        tried.append(name)
        call_kwargs = kwargs
        owner_key = _resolve_owner_key(
            name, tenant_id=tenant_id, project_slug=project_slug, user_subject=user_subject
        )
        if owner_key:
            call_kwargs = {**kwargs, "api_key": owner_key}
        leg_model = (models or {}).get(name) or model
        spoken: List[str] = []
        final: Optional[ProviderResponse] = None
        # Held by name so it can be closed by hand: `async for` does not close
        # an async generator the consumer abandons — that waits for the
        # garbage collector — and the HTTP stream inside it would go on
        # reading tokens nobody will see after the developer pressed Stop.
        leg = provider.stream(prompt, model=leg_model, **call_kwargs)
        try:
            yield {"type": "provider", "name": name, "streams": bool(getattr(provider, "streams", False))}
            async for ev in leg:
                if ev.delta:
                    spoken.append(ev.delta)
                    yielded_delta = True
                    yield {"type": "delta", "text": ev.delta}
                if ev.final is not None:
                    final = ev.final
            if final is None:
                raise ProviderError(
                    f"{name} stream ended without a result", provider=name, transient=True
                )
            final.providers_tried = list(tried)
            await default_breaker.record_success(breaker_id)
            _health.note_success(name, tenant=tenant_id, model=str(final.model or leg_model or ""))
            if use_cache:
                await default_cache.set(cache_key, final)
            _meter(final, provider=name, tenant_id=tenant_id)
            _record_quota(
                name,
                tenant_id=tenant_id,
                tokens=int(final.tokens_in or 0) + int(final.tokens_out or 0),
                status_code=200,
                model=final.model or (model or ""),
            )
            yield {"type": "done", "response": final}
            return
        except (ProviderError, *_TRANSIENT_INFRA_EXCEPTIONS) as exc:
            last_err = exc
            transient = getattr(exc, "transient", True)
            saw_transient = saw_transient or transient
            rate_limited = rate_limited or _looks_rate_limited(exc)
            generation_failed = generation_failed or _looks_generation_failure(exc)
            rate_limit_wait = max(rate_limit_wait, _retry_hint(exc))
            await default_breaker.record_failure(breaker_id)
            _health.note_failure(
                name, tenant=tenant_id, permanent=not transient,
                detail=str(exc), model=str(leg_model or ""),
            )
            if isinstance(exc, ProviderError):
                _record_quota(name, tenant_id=tenant_id, status_code=500, exc=exc)
            if spoken:
                # Text already reached the developer. Failing over now would
                # show a second answer under a half one; the honest end is to
                # say what happened and keep what was said.
                logger.info("provider %s failed mid-answer: %s", name, exc)
                yield {
                    "type": "error",
                    "detail": str(exc)[:400],
                    "partial": "".join(spoken),
                    "providers_tried": list(tried),
                }
                return
            logger.info(
                "provider %s failed before answering (%s), trying the next one: %s",
                name, "transient" if transient else "permanent", exc,
            )
            # Said out loud, not only logged: a developer who chose this
            # provider is owed the reason the answer came from another.
            yield {
                "type": "leg_failed",
                "name": name,
                "detail": str(exc)[:200],
                "transient": bool(transient),
            }
            continue
        finally:
            await leg.aclose()

    if last_err is not None and not saw_transient and isinstance(last_err, ProviderError):
        raise last_err
    if saw_transient and (rate_limited or generation_failed) and not _second_pass and not yielded_delta:
        wait = rate_limit_wait if rate_limited else 0.0
        logger.info(
            "every provider in the chain %s; one more pass after %.1fs",
            "was rate-limited" if rate_limited else "rejected its own generation",
            wait,
        )
        await asyncio.sleep(wait)
        async for ev in stream_with_cascade(prompt, primary=primary, model=model, models=models, fallbacks=fallbacks, use_cache=use_cache, tenant_id=tenant_id, project_slug=project_slug, user_subject=user_subject, _second_pass=True, **kwargs):
            yield ev
        return
    raise CascadeUnavailable(
        "every provider in the chain failed; some may recover shortly",
        providers_tried=tried,
        last_error=last_err,
    )
