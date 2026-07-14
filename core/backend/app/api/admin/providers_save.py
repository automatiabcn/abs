# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Provider config SAVE endpoint."""

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

# Provider id → registry name (app.providers.registry.get_provider). 1:1 —
# cloudflare is registered as "cloudflare"; the old "cloudflare_workers_ai"
# was unknown to the registry, so the save live-test 503'd and bad Cloudflare
# credentials were silently accepted instead of rejected.
_PROVIDER_RUNTIME_NAME: Dict[str, str] = {
    "groq": "groq",
    "cerebras": "cerebras",
    "cloudflare": "cloudflare",
    "gemini": "gemini",
    "cohere": "cohere",
    "anthropic": "anthropic",
}

_TEST_PROMPT = "Reply with the single word OK."


class ProviderSave(BaseModel):
    api_key: SecretStr = Field(..., min_length=1, max_length=512)
    enabled: bool = True
    # Cloudflare Workers AI also needs an account id alongside the API token.
    # Optional + ignored for every other provider (they have no account_id).
    account_id: Optional[str] = Field(default=None, max_length=128)


def _full_mask(provider_id: str) -> str:
    if provider_id == "anthropic":
        return "sk-ant-" + ("•" * 12)
    return "sk-" + ("•" * 12)


class _PersistError(RuntimeError):
    """raised when vault/env persistence cannot be
    completed atomically. The caller is expected to translate this to
    HTTP 500 + rollback the in-memory ``settings`` attribute."""


def _persist_secret(
    provider_id: str, value: str, previous: Optional[str] = None
) -> Dict[str, bool]:
    """atomic vault + .env persistence.

    Previous behaviour swallowed every ``Exception`` so a vault write
    that succeeded followed by an ``IOError`` on the .env patch left a
    half-persisted state: the UI returned 200, but the next boot reloaded
    settings from ``.env`` and the key was gone (vault is a side-channel
    in dev). Now both writes must succeed; on .env failure we roll the
    vault back to ``previous`` (or delete it if ``previous`` is empty).
    """
    attr = _PROVIDER_ATTR[provider_id]
    env_key = f"ABS_{attr.upper()}"
    from app.api.setup import _persist_encrypted_secret, _persist_env_var

    try:
        vault_ok = bool(_persist_encrypted_secret(attr, value))
    except Exception as exc:
        logger.warning("vault write failed provider=%s err=%s", provider_id, exc)
        raise _PersistError(f"vault_write_failed:{type(exc).__name__}") from exc

    try:
        env_ok = bool(_persist_env_var(env_key, value))
    except Exception as exc:
        logger.warning(
            "env write failed provider=%s err=%s — rolling vault back",
            provider_id,
            exc,
        )
        # Best-effort rollback so the boot doesn't see a half-persisted state.
        try:
            if previous:
                _persist_encrypted_secret(attr, previous)
            else:
                from app.vault.runner import delete_secret

                delete_secret(attr)
        except Exception as rb_exc:  # pragma: no cover
            logger.error(
                "vault rollback also failed provider=%s err=%s",
                provider_id,
                rb_exc,
            )
        raise _PersistError(f"env_write_failed:{type(exc).__name__}") from exc

    if not vault_ok and not env_ok:
        # Neither vault nor .env accepted the write (vault
        # uninitialised — init_vault.sh not run — AND no writable .env). The
        # previous code returned silently here, so save_provider replied 200
        # "configured" while the key was actually persisted NOWHERE and lost on
        # the next restart. Fail loud so the panel surfaces a real error.
        raise _PersistError(
            "no_persistence_target: vault uninitialised (run scripts/init_vault.sh) "
            "and .env not writable"
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
            _persist_env_var(f"ABS_{flag_attr.upper()}", "true" if enabled else "false")
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
            # 256 (was 8): reasoning models — e.g. Cerebras' default
            # gpt-oss-120b — emit no parseable completion under a tiny token
            # budget, so a *valid* key could fail its own save test. A
            # connectivity check costs ~nothing extra at 256.
            max_tokens=256,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "model": getattr(resp, "model", None),
            "latency_ms": latency_ms,
            "transient": False,
        }
    except ProviderError as exc:
        # The cascade re-raises a ProviderError ONLY when it is non-transient
        # (bad key / 4xx / unknown model) — a definitive auth/config failure.
        # CodeQL py/stack-trace-exposure (#46). ProviderError
        # carries a curated `.message` (no Python frame), so we can surface it
        # as a short code. Defense-in-depth: cap length, strip newlines.
        latency_ms = int((time.perf_counter() - started) * 1000)
        safe_msg = (str(exc.message or "") or "provider_error").splitlines()[0][:120]
        return {
            "ok": False,
            "error": safe_msg or "provider_error",
            "latency_ms": latency_ms,
            "transient": bool(getattr(exc, "transient", False)),
        }
    except HTTPException as exc:
        # call_with_cascade raises 503 when EVERY attempt failed transiently
        # (timeout / 5xx / rate-limit / thin unparseable response). The
        # provider was reachable, so the key may well be valid — mark it
        # transient so the caller persists it with a soft warning instead of
        # discarding a good key over a flaky ping.
        latency_ms = int((time.perf_counter() - started) * 1000)
        if exc.status_code == 503:
            return {
                "ok": False,
                "error": "provider_unreachable_transient",
                "latency_ms": latency_ms,
                "transient": True,
            }
        raise
    except Exception:  # pragma: no cover
        latency_ms = int((time.perf_counter() - started) * 1000)
        # Opaque request_id pattern: log full trace
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
            "transient": False,
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

    # Cloudflare Workers AI needs an account id beside the token. Apply it to
    # the live settings BEFORE the connectivity test so the ping can reach
    # /accounts/{id}/ai/run/…; persisted further below next to the token.
    cf_account_new = (
        (body.account_id or "").strip() if provider_id == "cloudflare" else ""
    )
    cf_account_prev = getattr(settings, "cf_account_id", "")
    if provider_id == "cloudflare" and cf_account_new:
        setattr(settings, "cf_account_id", cf_account_new)

    test_result: Dict[str, Any] = {
        "ok": True,
        "latency_ms": 0,
        "skipped": True,
    }
    if raw_key and body.enabled:
        test_result = await _live_test_provider(provider_id)
        # Reject ONLY on a definitive (non-transient) failure — a bad key /
        # 4xx / unknown model. A transient failure (timeout / 5xx / rate-limit /
        # thin reasoning-model response) means the provider was reachable and
        # the key is probably fine; persist it with a soft warning rather than
        # discarding a valid key over a flaky ping. (This is why a working
        # Cerebras key — HTTP 200 upstream — used to 422 and get reverted.)
        if not test_result.get("ok") and not test_result.get("transient"):
            setattr(settings, attr, previous)
            if provider_id == "cloudflare" and cf_account_new:
                setattr(settings, "cf_account_id", cf_account_prev)
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

    try:
        persist_status = _persist_secret(
            provider_id, raw_key, previous=str(previous or "")
        )
    except _PersistError as exc:
        # Revert in-memory setting so the runtime matches disk.
        setattr(settings, attr, previous)
        emit_event(
            request,
            action="admin.provider.save",
            outcome="error",
            reason="persist_failed",
            provider=provider_id,
            error_class=str(exc),
            status_code=500,
        )
        raise HTTPException(
            500,
            {
                "error": "provider_key_persist_failed",
                "detail": str(exc),
            },
        )
    # Persist the Cloudflare account id alongside the token (same vault + .env
    # channels). Best-effort: a failure here is logged but doesn't 500 the save
    # — the token already landed and the account id stays in live settings.
    if provider_id == "cloudflare" and cf_account_new:
        try:
            from app.api.setup import _persist_encrypted_secret, _persist_env_var

            _persist_encrypted_secret("cf_account_id", cf_account_new)
            _persist_env_var("ABS_CF_ACCOUNT_ID", cf_account_new)
        except Exception as exc:  # pragma: no cover
            logger.warning("cf_account_id persist failed: %s", exc)

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
