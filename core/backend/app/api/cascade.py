# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Phase 10 — `/v1/cascade/run` HTTP route.

Wraps the `providers.cascade` library + `anthropic_mock` adapter so a
client can issue a completion request and see the cascade chain in action.

Auth: panel session cookie (`current_admin`).

Modes:
* `anthropic_mock_mode` set — uses the deterministic mock so tests
  can exercise rate-limit / timeout / 500 fallback paths without a key.
* No mock + provider keys configured — *would* call the real provider
  cascade. Live cascade (Groq + Cerebras + Gemini real calls) is gated on
  the operator vault key; for now the route returns a clear
  503 if no mock is set and the operator hasn't supplied a primary key.

Response shape mirrors the brief: `{completion, provider, fallback_chain,
tokens_used}`.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import current_admin
from app.cascade.orchestrator import call_with_cascade
from app.config import settings
from app.providers.anthropic_mock import (
    RateLimitError,
    get_mock_provider,
)
from app.providers.cascade import (
    PROVIDER_ORDER,
    configured_map,
    get_active_providers,
)
from app.providers.schemas import CascadeUnavailable, ProviderError
from app.services import feature_usage as feature_usage_service
from app.services import usage_log

router = APIRouter(prefix="/v1/cascade", tags=["cascade"])
logger = logging.getLogger(__name__)


class CascadeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    prefer: Optional[str] = None
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    model: Optional[str] = None
    use_cache: bool = True
    skip_paid_providers: bool = False


class CascadeResponse(BaseModel):
    completion: str
    provider: str
    fallback_chain: List[str]
    tokens_used: int
    mock: bool = False
    cached: bool = False
    elapsed_ms: int = 0
    model: str = ""


@router.get("/providers")
async def list_providers(
    request: Request, admin: dict = Depends(current_admin)
) -> dict:
    """The chain that will actually answer *this* caller.

    It used to be the chain that would answer a caller with no keys of their own,
    which is a different thing the moment anyone brings one: a provider they
    supplied a key for showed up under "missing", and the order on screen was not
    the order their questions would take. The panel's whole job here is to tell
    someone who is about to answer them.
    """
    from app.api.chat import _resolve_tenant

    subject = str(admin.get("sub") or "")
    tenant = _resolve_tenant(subject) or "_global"
    project = request.headers.get("X-Project-Id") or None

    owned: frozenset[str] = frozenset()
    if tenant and tenant != "_global":
        try:
            from app.multitenant.provider_keys import tenant_configured_providers

            owned = frozenset(
                tenant_configured_providers(
                    tenant_slug=tenant, project_slug=project, user_subject=subject
                )
            )
        except Exception:  # noqa: BLE001 — BYOK is a bonus, never a blocker
            owned = frozenset()

    cfg = configured_map()
    active = get_active_providers(extra_configured=owned)
    missing = [p for p in PROVIDER_ORDER if not cfg.get(p, False) and p not in owned]
    return {
        "active": active,
        "missing": missing,
        "configured_count": len(active),
        "total": len(PROVIDER_ORDER),
        # Which of these are the caller's own keys, so the panel can say so
        # rather than leaving them to guess whose bill a question lands on.
        "byok": sorted(owned),
        "anthropic_mock_mode": getattr(settings, "anthropic_mock_mode", "off"),
    }


async def _try_mock(
    request: CascadeRequest, fallback_chain: List[str]
) -> Optional[CascadeResponse]:
    """If anthropic_mock_mode is on, prefer it as the primary. On failure,
    record the attempt in fallback_chain and return None so the caller
    knows to continue to the next provider."""
    mock = get_mock_provider()
    if mock is None:
        return None
    fallback_chain.append("anthropic-mock")
    try:
        resp = await mock.complete(request.prompt)
        usage_log.append("anthropic", tokens=resp.tokens, tenant_slug="default")
        return CascadeResponse(
            completion=resp.completion,
            provider="anthropic-mock",
            fallback_chain=fallback_chain,
            tokens_used=resp.tokens,
            mock=True,
        )
    except (RateLimitError, TimeoutError, ProviderError) as exc:
        logger.info("cascade mock fell through: %s", exc)
        return None


@router.post("/run", response_model=CascadeResponse)
async def run(
    body: CascadeRequest,
    request: Request,
    admin: dict = Depends(current_admin),
) -> CascadeResponse:
    fallback_chain: List[str] = []

    # MT Phase 1 — per-owner (user/project) key context for BYOK.
    from app.api.chat import _resolve_tenant

    _user = str(admin.get("sub") or "")
    _tenant = _resolve_tenant(_user) or "_global"
    _project = request.headers.get("X-Project-Id") or None
    _extra: frozenset[str] = frozenset()
    if _tenant and _tenant != "_global":
        try:
            from app.multitenant.provider_keys import tenant_configured_providers

            _extra = frozenset(
                tenant_configured_providers(
                    tenant_slug=_tenant, project_slug=_project, user_subject=_user
                )
            )
        except Exception:  # noqa: BLE001
            _extra = frozenset()

    # 1. Try mock if enabled (test-only happy path).
    mock_result = await _try_mock(body, fallback_chain)
    if mock_result is not None:
        try:
            feature_usage_service.increment(
                "cascade_provider_call", actor_email=admin.get("sub")
            )
        except Exception:
            pass
        return mock_result

    # 2. Real cascade gate — needs at least one configured provider.
    active = get_active_providers(
        prefer=body.prefer, skip_paid=body.skip_paid_providers, extra_configured=_extra
    )
    if not active:
        if body.skip_paid_providers:
            raise HTTPException(
                503,
                "no_free_providers_configured: skip_paid_providers=true but "
                "no free provider keys (groq/cerebras/gemini/cohere/cloudflare) "
                "are configured",
            )
        raise HTTPException(
            503,
            "no_providers_configured: configure at least one API key "
            "or enable ABS_ANTHROPIC_MOCK_MODE for test runs",
        )

    # 3. Real provider cascade — call_with_cascade walks the active chain
    #    (cache → breaker → fallback). Configured-but-unregistered providers
    #    (e.g. anthropic gated by ABS_ANTHROPIC_ENABLED) raise inside the
    #    orchestrator and the loop falls through to the next.
    primary, *rest = active
    try:
        resp = await call_with_cascade(
            body.prompt,
            primary=primary,
            model=body.model,
            fallbacks=tuple(rest),
            use_cache=body.use_cache,
            max_tokens=body.max_tokens,
            tenant_id=_tenant,
            project_slug=_project,
            user_subject=_user or None,
        )
    except CascadeUnavailable:
        # Busy, not broken: the app's handler answers 503 + Retry-After. A 502
        # here would tell the caller to stop trying, which is the opposite of
        # what is true.
        raise
    except ProviderError as exc:
        # Every provider failed for good: a bad key, a missing model. Retrying
        # will not help, and 502 says so.
        raise HTTPException(
            502,
            f"all_providers_failed: {exc.message or str(exc)} "
            f"(chain={','.join(active)})",
        ) from exc

    fallback_chain.append(resp.provider or primary)
    tokens_used = (resp.tokens_in or 0) + (resp.tokens_out or 0)
    # Metering moved into the cascade itself (`orchestrator._meter`), which is
    # the one place every answered request passes through. Recording it here as
    # well would count this route's traffic twice — and recording it *only* here
    # was the bug: chat, agents and workflows all go through the cascade without
    # coming through this route, so none of them ever reached the usage page.
    try:
        feature_usage_service.increment(
            "cascade_provider_call", actor_email=admin.get("sub")
        )
    except Exception:
        pass

    return CascadeResponse(
        completion=resp.text,
        provider=resp.provider or primary,
        fallback_chain=fallback_chain,
        tokens_used=tokens_used,
        mock=False,
        cached=resp.cached,
        elapsed_ms=resp.elapsed_ms,
        model=resp.model,
    )


# Re-export for tests/util that want to bypass the route.
__all__ = ["CascadeRequest", "CascadeResponse", "router"]
