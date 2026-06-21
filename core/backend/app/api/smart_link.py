# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""026 — Smart Link production: OAuth, vault encrypt, provider validate, dashboard.

Endpoints:
  GET    /v1/smart-link/providers          — supported integrations list
  POST   /v1/smart-link/github/authorize   — OAuth start (DB-backed state, 10min TTL)
  GET    /v1/smart-link/github/callback    — code → token (mock httpx in tests)
  POST   /v1/smart-link/github/refresh     — refresh token rotation (admin)
  DELETE /v1/smart-link/github             — revoke + clear DB (admin)
  POST   /v1/smart-link/api-key            — provider + api_key validate + vault store
  GET    /v1/smart-link/connected-services — DB list (admin, no plaintext)
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import settings
from app.db.models import OAuthState
from app.db.session import get_engine
from app.observability.audit import emit_event  # Q12-L23 sweep 4
from app.smart_link.provider_validators import VALIDATORS, validate as validate_provider
from app.smart_link.vault_secrets import (
    decrypt_secret,
    delete_secret,
    encrypt_secret,
    list_secrets,
    rotate_secret,
    update_validation_status,
)

router = APIRouter(prefix="/v1/smart-link", tags=["smart-link"])
logger = logging.getLogger(__name__)


_SUPPORTED_PROVIDERS = [
    {
        "id": "github",
        "name": "GitHub",
        "auth_method": "oauth",
        "scopes": ["repo", "read:user"],
    },
    {
        "id": "slack",
        "name": "Slack",
        "auth_method": "oauth",
        "scopes": ["chat:write", "channels:read"],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "auth_method": "api_key",
        "validate_endpoint": "https://api.openai.com/v1/models",
    },
    {
        "id": "anthropic",
        "name": "Anthropic",
        "auth_method": "api_key",
        "validate_endpoint": "https://api.anthropic.com/v1/messages",
    },
    {
        "id": "cohere",
        "name": "Cohere",
        "auth_method": "api_key",
        "validate_endpoint": "https://api.cohere.ai/v1/models",
    },
    {
        "id": "groq",
        "name": "Groq",
        "auth_method": "api_key",
        "validate_endpoint": "https://api.groq.com/openai/v1/models",
    },
    {
        "id": "gemini",
        "name": "Gemini",
        "auth_method": "api_key",
        "validate_endpoint": "https://generativelanguage.googleapis.com/v1beta/models",
    },
    {
        "id": "smtp",
        "name": "SMTP",
        "auth_method": "credentials",
    },
]


_STATE_TTL = timedelta(minutes=10)


def _check_admin(
    authorization: Optional[str], request: Optional[Request] = None
) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        emit_event(
            request,
            action="smart_link.admin.gate",
            outcome="denied",
            reason="missing_bearer",
            status_code=401,
        )
        raise HTTPException(401, "Authorization header missing")
    parts = authorization.split(None, 1)
    token = parts[1].strip() if len(parts) > 1 else ""
    if not token:
        emit_event(
            request,
            action="smart_link.admin.gate",
            outcome="denied",
            reason="empty_bearer",
            status_code=401,
        )
        raise HTTPException(401, "Authorization header missing")
    if not settings.admin_token or token != settings.admin_token:
        emit_event(
            request,
            action="smart_link.admin.gate",
            outcome="denied",
            reason="admin_token_invalid",
            status_code=403,
        )
        raise HTTPException(403, "Invalid admin token")


def _new_state(provider: str, redirect_url: str) -> str:
    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        # Purge expired states
        rows = db.scalars(select(OAuthState)).all()
        for r in rows:
            ts = r.created_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if now - ts > _STATE_TTL:
                db.delete(r)
        db.add(
            OAuthState(state=state, provider=provider, redirect_url=redirect_url)
        )
        db.commit()
    return state


def _consume_state(state: str, provider: str) -> Optional[str]:
    """Pop state once; returns redirect_url or None if invalid/expired/replayed."""
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        row = db.scalars(
            select(OAuthState).where(OAuthState.state == state)
        ).first()
        if row is None:
            return None
        ts = row.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if now - ts > _STATE_TTL:
            db.delete(row)
            db.commit()
            return None
        if row.provider != provider:
            return None
        redirect = row.redirect_url
        db.delete(row)
        db.commit()
    return redirect


# ---- Schemas ----------------------------------------------------------------


class GithubAuthorizeRequest(BaseModel):
    redirect_url: str
    client_id: Optional[str] = None


class GithubAuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


class ApiKeyStoreRequest(BaseModel):
    provider: str
    api_key: str


class ApiKeyStoreResponse(BaseModel):
    ok: bool
    provider: str
    stored: bool
    validated: bool
    latency_ms: float


# ---- Endpoints --------------------------------------------------------------


@router.get("/providers")
async def list_providers() -> dict:
    return {"providers": _SUPPORTED_PROVIDERS}


@router.post("/github/authorize", response_model=GithubAuthorizeResponse)
async def github_authorize(body: GithubAuthorizeRequest) -> GithubAuthorizeResponse:
    state = _new_state("github", body.redirect_url)
    client_id = body.client_id or "abs_github_client_skeleton"
    scopes = "repo%20read%3Auser"
    authorize_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={client_id}&scope={scopes}&state={state}"
    )
    return GithubAuthorizeResponse(authorize_url=authorize_url, state=state)


@router.get("/github/callback")
async def github_callback(code: str, state: str, request: Request) -> dict:
    redirect = _consume_state(state, "github")
    if redirect is None:
        # Q12-L23 sweep 4 — emit BEFORE raising. Replayed/forged/expired
        # OAuth state is *exactly* the kind of probe ops needs to see.
        emit_event(
            request,
            action="smart_link.github.callback",
            outcome="denied",
            reason="state_invalid_or_expired",
            status_code=400,
            provider="github",
        )
        raise HTTPException(400, "Invalid or expired state")

    # Real flow POSTs to GitHub /login/oauth/access_token. Tests monkeypatch httpx.
    token: Optional[str] = None
    error: Optional[str] = None
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                json={
                    "client_id": getattr(settings, "github_client_id", ""),
                    "client_secret": getattr(
                        settings, "github_client_secret", ""
                    ),
                    "code": code,
                    "state": state,
                },
            )
            if r.status_code == 200:
                data = r.json() if hasattr(r, "json") else {}
                token = data.get("access_token") if isinstance(data, dict) else None
            else:
                error = f"HTTP {r.status_code}"
    except Exception as exc:
        logger.exception("github smart_link callback failed")
        error = type(exc).__name__

    if token:
        encrypt_secret(
            key_name="github_oauth_token", provider="github", value=token
        )
        update_validation_status(
            key_name="github_oauth_token", ok=True, error=None
        )
        emit_event(
            request,
            action="smart_link.github.callback",
            outcome="success",
            provider="github",
        )
    else:
        emit_event(
            request,
            action="smart_link.github.callback",
            outcome="failure",
            reason="token_exchange_failed",
            provider="github",
        )

    return {
        "ok": token is not None,
        "provider": "github",
        "code_received": True,
        "token_stored_via_vault": token is not None,
        "error": error,
        "redirect_url": redirect,
    }


@router.post("/github/refresh")
async def github_refresh(
    request: Request, authorization: Optional[str] = Header(default=None)
) -> dict:
    _check_admin(authorization, request)
    current = decrypt_secret("github_oauth_token")
    if current is None:
        emit_event(
            request,
            action="smart_link.github.refresh",
            outcome="denied",
            reason="no_token_stored",
            status_code=404,
            provider="github",
        )
        raise HTTPException(404, "No GitHub token stored")
    rotate_secret(
        key_name="github_oauth_token", provider="github", new_value=current
    )
    emit_event(
        request,
        action="smart_link.github.refresh",
        outcome="success",
        provider="github",
    )
    return {"ok": True, "provider": "github", "rotated": True}


@router.delete("/github")
async def github_revoke(
    request: Request, authorization: Optional[str] = Header(default=None)
) -> dict:
    _check_admin(authorization, request)
    deleted = delete_secret("github_oauth_token")
    emit_event(
        request,
        action="smart_link.github.revoke",
        outcome="success",
        provider="github",
        count=int(bool(deleted)),
    )
    return {"ok": True, "deleted": deleted}


@router.post("/api-key", response_model=ApiKeyStoreResponse)
async def store_api_key(body: ApiKeyStoreRequest, request: Request) -> ApiKeyStoreResponse:
    valid_ids = {p["id"] for p in _SUPPORTED_PROVIDERS}
    if body.provider not in valid_ids:
        emit_event(
            request,
            action="smart_link.api_key.store",
            outcome="denied",
            reason="unsupported_provider",
            status_code=400,
            provider=str(body.provider)[:32],
        )
        raise HTTPException(400, f"Unsupported provider: {body.provider}")
    if not body.api_key or len(body.api_key) < 8:
        emit_event(
            request,
            action="smart_link.api_key.store",
            outcome="denied",
            reason="api_key_too_short",
            status_code=400,
            provider=body.provider,
        )
        raise HTTPException(400, "API key too short")

    if body.provider in VALIDATORS:
        result = validate_provider(body.provider, body.api_key)
        if not result["ok"]:
            emit_event(
                request,
                action="smart_link.api_key.store",
                outcome="denied",
                reason="provider_validation_failed",
                status_code=422,
                provider=body.provider,
            )
            raise HTTPException(
                422, f"Provider validation failed: {result.get('error')}"
            )
        latency = result["latency_ms"]
        validated = True
    else:
        latency = 0.0
        validated = False

    key_name = f"{body.provider}_api_key"
    encrypt_secret(key_name=key_name, provider=body.provider, value=body.api_key)
    update_validation_status(key_name=key_name, ok=True, error=None)
    emit_event(
        request,
        action="smart_link.api_key.store",
        outcome="success",
        provider=body.provider,
        duration_ms=latency,
    )
    return ApiKeyStoreResponse(
        ok=True,
        provider=body.provider,
        stored=True,
        validated=validated,
        latency_ms=latency,
    )


@router.get("/connected-services")
async def connected_services(
    request: Request, authorization: Optional[str] = Header(default=None)
) -> dict:
    _check_admin(authorization, request)
    secrets_list = list_secrets()
    return {
        "providers": _SUPPORTED_PROVIDERS,
        "connected": secrets_list,
        "count": len(secrets_list),
    }


_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/connect", include_in_schema=False)
async def connect_dashboard() -> FileResponse:
    """Static HTML connect dashboard (admin token required client-side)."""
    return FileResponse(_STATIC_DIR / "connect.html", media_type="text/html")
