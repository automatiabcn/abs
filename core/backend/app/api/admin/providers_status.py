# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Polish round R7 — provider key configuration status (no secrets exposed).

The Settings → Sağlayıcılar tab needs to render a status badge per provider
without ever shipping the raw API key to the browser. This endpoint reports
whether each cascade provider is configured (true/false) plus a small
``label`` map the UI can use as the canonical capitalised name.

GET /v1/admin/providers/status

Sprint 2B BUG-33 extends this router with:

POST /v1/admin/providers/{id}/test  — synthetic prompt against the named
                                       cascade provider; returns latency
                                       + ok/error so the operator can
                                       confirm the key actually works
                                       without flipping the global
                                       ``ABS_*_ENABLED`` flag.

Auth: ``admin_required``. Requires the admin Bearer token / cookie issued
by ``/v1/admin/auth/login`` — same surface as every other ``/v1/admin/*``.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.admin.auth import admin_required
from app.config import settings
from app.middleware.rate_limit import limiter
from app.observability.audit import emit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin/providers", tags=["admin", "providers"])


# Canonical display labels + the settings attribute that holds each key.
# Capitalisation is owned by the backend so every consumer (UI, CLI,
# webhook payload) stays consistent; this also makes the wire payload the
# single source of truth instead of duplicating a label map in the React
# component.
#
# Order MUST mirror `cascade.PROVIDER_ORDER_DEFAULT` (free-first, Anthropic
# last) so the Providers page cascade visual matches the real runtime order.
_PROVIDERS: List[Dict[str, str]] = [
    {"id": "groq", "label": "Groq", "attr": "groq_api_key"},
    {"id": "cerebras", "label": "Cerebras", "attr": "cerebras_api_key"},
    {"id": "gemini", "label": "Gemini", "attr": "gemini_api_key"},
    {"id": "cohere", "label": "Cohere", "attr": "cohere_api_key"},
    {"id": "cloudflare", "label": "Cloudflare", "attr": "cf_api_token"},
    {"id": "anthropic", "label": "Anthropic", "attr": "anthropic_api_key"},
]


@router.get("/status")
async def providers_status(_admin: dict = Depends(admin_required)) -> Dict[str, Any]:
    """Return per-provider configured-or-not status without exposing keys."""
    items = []
    for spec in _PROVIDERS:
        raw = getattr(settings, spec["attr"], "") or ""
        configured = bool(raw.strip())
        # Cloudflare Workers AI needs BOTH the API token (cf_api_token) AND the
        # account id (cf_account_id) — its run URL is /accounts/{id}/ai/run/….
        # Without this, a token-only save reported "configured" but every call
        # failed at runtime with "account_id veya api_token tanımlı değil".
        if spec["id"] == "cloudflare":
            account = getattr(settings, "cf_account_id", "") or ""
            configured = configured and bool(account.strip())
        items.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "configured": configured,
            }
        )
    return {"providers": items}


# ---------- Sprint 2B BUG-33 — provider test endpoint ---------------------


_TEST_PROMPT = "Reply with the single word OK."
# Provider id → cascade-runtime provider name (matches
# `app.providers.registry.get_provider`). These line up 1:1 — the registry
# registers CloudflareProvider under "cloudflare" (NOT "cloudflare_workers_ai";
# that stale name made get_provider raise → the live test 503'd → bad creds
# were silently accepted).
_PROVIDER_RUNTIME_NAME: Dict[str, str] = {
    "groq": "groq",
    "cerebras": "cerebras",
    "cloudflare": "cloudflare",
    "gemini": "gemini",
    "cohere": "cohere",
    "anthropic": "anthropic",
}


def _provider_spec(provider_id: str) -> Optional[Dict[str, str]]:
    return next((p for p in _PROVIDERS if p["id"] == provider_id), None)


@router.post("/{provider_id}/test")
@limiter.limit("5/minute")
async def test_provider(
    provider_id: str,
    request: Request,
    _admin: dict = Depends(admin_required),
) -> Dict[str, Any]:
    """Run a synthetic single-token prompt through the named provider.

    The endpoint is read-only side-effect-wise: no key write, no flag
    flip. It only ever measures whether the operator's stored key is
    accepted and returns ``{ok, latency_ms, model?, error?}``.

    Sprint 2I UAT-019 — `@limiter.limit("5/minute")` caps abusive
    automation that would otherwise burn through real provider quota
    on every keystroke.
    """
    spec = _provider_spec(provider_id)
    if spec is None:
        emit_event(
            request,
            action="setup.provider.test",
            outcome="denied",
            reason="unknown_provider",
            provider=provider_id,
            status_code=404,
        )
        raise HTTPException(status_code=404, detail="unknown_provider")

    raw_key = (getattr(settings, spec["attr"], "") or "").strip()
    if not raw_key:
        emit_event(
            request,
            action="setup.provider.test",
            outcome="denied",
            reason="missing_api_key",
            provider=provider_id,
            status_code=400,
        )
        return {
            "ok": False,
            "provider": provider_id,
            "error": "missing_api_key",
            "latency_ms": 0,
        }

    # Lazy import to keep `from app.api.admin.providers_status` cheap on
    # boot (cascade pulls in httpx + breaker state on first import).
    from app.cascade.orchestrator import call_with_cascade
    from app.providers.schemas import ProviderError

    runtime = _PROVIDER_RUNTIME_NAME.get(provider_id, provider_id)
    started = time.perf_counter()
    try:
        resp = await call_with_cascade(
            _TEST_PROMPT,
            primary=runtime,
            fallbacks=(),
            use_cache=False,
            max_tokens=8,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        emit_event(
            request,
            action="setup.provider.test",
            outcome="success",
            provider=provider_id,
            duration_ms=latency_ms,
        )
        return {
            "ok": True,
            "provider": provider_id,
            "model": getattr(resp, "model", None),
            "latency_ms": latency_ms,
        }
    except ProviderError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        emit_event(
            request,
            action="setup.provider.test",
            outcome="failure",
            provider=provider_id,
            duration_ms=latency_ms,
            reason="provider_error",
            error_class=type(exc).__name__,
        )
        return {
            "ok": False,
            "provider": provider_id,
            "error": str(exc.message or exc) or "provider_error",
            "latency_ms": latency_ms,
        }
    except Exception as exc:  # pragma: no cover — unexpected
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.warning("provider_test_unexpected provider=%s err=%s", provider_id, exc)
        emit_event(
            request,
            action="setup.provider.test",
            outcome="error",
            provider=provider_id,
            duration_ms=latency_ms,
            error_class=type(exc).__name__,
        )
        return {
            "ok": False,
            "provider": provider_id,
            "error_class": type(exc).__name__,
            "latency_ms": latency_ms,
        }
