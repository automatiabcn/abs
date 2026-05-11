# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sprint 2C ITEM-2 - Provider config SAVE endpoint."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr

from app.api.admin.auth import admin_required
from app.config import settings
from app.observability.audit import emit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin/providers", tags=["admin", "providers"])


_PROVIDER_ATTR: Dict[str, str] = {
    "groq": "groq_api_key",
    "cerebras": "cerebras_api_key",
    "cloudflare": "cf_api_token",
    "gemini": "gemini_api_key",
    "cohere": "cohere_api_key",
    "anthropic": "anthropic_api_key",
}

_PROVIDER_ENABLED_FLAG: Dict[str, Optional[str]] = {
    "groq": None,
    "cerebras": None,
    "cloudflare": None,
    "gemini": None,
    "cohere": None,
    "anthropic": "anthropic_enabled",
}

_PROVIDER_RUNTIME_NAME: Dict[str, str] = {
    "groq": "groq",
    "cerebras": "cerebras",
    "cloudflare": "cloudflare_workers_ai",
    "gemini": "gemini",
    "cohere": "cohere",
    "anthropic": "anthropic",
}

_TEST_PROMPT = "Reply with the single word OK."


class ProviderSave(BaseModel):
    api_key: SecretStr = Field(..., min_length=1, max_length=512)
    enabled: bool = True


def _full_mask(provider_id: str) -> str:
    if provider_id == "anthropic":
        return "sk-ant-" + ("•" * 12)
    return "sk-" + ("•" * 12)


def _persist_secret(provider_id: str, value: str) -> Dict[str, bool]:
    attr = _PROVIDER_ATTR[provider_id]
    vault_ok = False
    env_ok = False
    try:
        from app.api.setup import (
            _persist_encrypted_secret,
            _persist_env_var,
        )

        vault_ok = bool(_persist_encrypted_secret(attr, value))
        env_ok = bool(_persist_env_var(f"ABS_{attr.upper()}", value))
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "provider_save persist failed provider=%s err=%s",
            provider_id,
            exc,
        )
    return {"vault": vault_ok, "env": env_ok}


def _persist_enabled_flag(provider_id: str, enabled: bool) -> bool:
    flag_attr = _PROVIDER_ENABLED_FLAG.get(provider_id)
    if not flag_attr:
        return False
    try:
        setattr(settings, flag_attr, enabled)
        from app.api.setup import _persist_env_var

        return bool(
            _persist_env_var(
                f"ABS_{flag_attr.upper()}", "true" if enabled else "false"
            )
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("enabled flag persist failed: %s", exc)
        return False


async def _invalidate_caches(provider_id: str) -> None:
    try:
        from app.cascade.cache import default_cache

        await default_cache.clear()
    except Exception as exc:  # pragma: no cover
        logger.warning("cache_clear failed: %s", exc)
    try:
        from app.cascade.breaker import default_breaker

        async with default_breaker._lock:  # noqa: SLF001
            state = default_breaker._states.get(  # noqa: SLF001
                _PROVIDER_RUNTIME_NAME.get(provider_id, provider_id)
            )
            if state is not None:
                state.state = "closed"
                state.fail_count = 0
                state.fail_window_start = 0.0
                state.opened_at = 0.0
    except Exception as exc:  # pragma: no cover
        logger.warning("breaker reset failed: %s", exc)


async def _live_test_provider(provider_id: str) -> Dict[str, Any]:
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
        return {
            "ok": True,
            "model": getattr(resp, "model", None),
            "latency_ms": latency_ms,
        }
    except ProviderError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        # Sprint 2D ITEM-2.3 — CodeQL py/stack-trace-exposure (#46). ProviderError
        # carries a curated `.message` (no Python frame), so we can surface it
        # as a short code. Defense-in-depth: cap length, strip newlines.
        safe_msg = (str(exc.message or "") or "provider_error").splitlines()[0][:120]
        return {
            "ok": False,
            "error": safe_msg or "provider_error",
            "latency_ms": latency_ms,
        }
    except Exception as exc:  # pragma: no cover
        latency_ms = int((time.perf_counter() - started) * 1000)
        # Sprint 2D ITEM-2.3 — opaque request_id pattern: log full trace
        # server-side, return only a correlation id to the caller.
        request_id = uuid.uuid4().hex[:12]
        logger.exception(
            "provider_test_failed provider=%s request_id=%s", provider_id, request_id
        )
        return {
            "ok": False,
            "error": "internal_error",
            "request_id": request_id,
            "latency_ms": latency_ms,
        }


@router.post("/{provider_id}")
async def save_provider(
    provider_id: str,
    body: ProviderSave,
    request: Request,
    _admin: dict = Depends(admin_required),
) -> Dict[str, Any]:
    if provider_id not in _PROVIDER_ATTR:
        emit_event(
            request,
            action="admin.provider.save",
            outcome="denied",
            reason="unknown_provider",
            provider=provider_id,
            status_code=404,
        )
        raise HTTPException(404, "unknown_provider")

    raw_key = body.api_key.get_secret_value().strip()

    if not raw_key and body.enabled:
        emit_event(
            request,
            action="admin.provider.save",
            outcome="denied",
            reason="empty_key_with_enabled",
            provider=provider_id,
            status_code=422,
        )
        raise HTTPException(422, "api_key_required_when_enabled")

    attr = _PROVIDER_ATTR[provider_id]
    previous = getattr(settings, attr, "")
    setattr(settings, attr, raw_key)

    test_result: Dict[str, Any] = {
        "ok": True,
        "latency_ms": 0,
        "skipped": True,
    }
    if raw_key and body.enabled:
        test_result = await _live_test_provider(provider_id)
        if not test_result.get("ok"):
            setattr(settings, attr, previous)
            emit_event(
                request,
                action="admin.provider.save",
                outcome="denied",
                reason="provider_test_failed",
                provider=provider_id,
                duration_ms=test_result.get("latency_ms"),
                error_class=test_result.get("error"),
                status_code=422,
            )
            raise HTTPException(
                422,
                {
                    "error": "provider_test_failed",
                    "detail": test_result.get("error"),
                    "latency_ms": test_result.get("latency_ms"),
                },
            )

    persist_status = _persist_secret(provider_id, raw_key)
    enabled_persisted = _persist_enabled_flag(provider_id, body.enabled)
    await _invalidate_caches(provider_id)

    emit_event(
        request,
        action="admin.provider.save",
        outcome="success",
        provider=provider_id,
        enabled=body.enabled,
        vault_persisted=persist_status["vault"],
        env_persisted=persist_status["env"],
        enabled_flag_persisted=enabled_persisted,
        test_ok=test_result.get("ok"),
        duration_ms=test_result.get("latency_ms"),
    )

    return {
        "provider_id": provider_id,
        "enabled": body.enabled,
        "configured": bool(raw_key),
        "masked_key": _full_mask(provider_id) if raw_key else "",
        "vault_persisted": persist_status["vault"],
        "env_persisted": persist_status["env"],
        "last_test": test_result,
    }
