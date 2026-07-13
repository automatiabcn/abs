# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""GDPR Article 17 (right to erasure) endpoints.

Two-step delete with 30-day grace:
  1. POST /v1/me/account/delete-request → email confirm JWT (24h exp, HS256)
  2. POST /v1/me/account/delete-confirm {token} → schedules purge T+30d
  3. POST /v1/me/account/delete-cancel  → unschedule (within grace window)

Actual data purge is performed by infra/scripts/purge_deleted_accounts.py
(daily cron) once `scheduled_delete_at <= now`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt as pyjwt
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import settings
from app.customer_audit.logger import log_customer_action
from app.db.models import License
from app.db.session import get_engine
from app.email.sender import send_account_delete_email
from app.licensing import verify_license
from app.observability.audit import emit_event

router = APIRouter(prefix="/v1/me/account", tags=["me"])
logger = logging.getLogger(__name__)

DELETE_TOKEN_TTL_HOURS = 24
GRACE_DAYS = 30


def _confirm_url(token: str) -> str:
    base = getattr(settings, "public_base_url", "") or "https://abs.automatiabcn.com"
    return f"{base.rstrip('/')}/account/delete-confirm?token={token}"


def _verify_bearer_license(
    authorization: Optional[str], request: Optional[Request] = None
) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        emit_event(
            request,
            action="me.account.auth",
            outcome="denied",
            reason="missing_bearer",
        )
        raise HTTPException(401, "Authorization Bearer license required")
    token = authorization.split(None, 1)[1].strip()
    try:
        payload = verify_license(token)
    except HTTPException:
        emit_event(
            request,
            action="me.account.auth",
            outcome="denied",
            reason="license_invalid",
        )
        raise
    except Exception as exc:
        emit_event(
            request,
            action="me.account.auth",
            outcome="error",
            reason="license_verify_exception",
            error_class=type(exc).__name__,
        )
        # Never leak the full exc string.
        raise HTTPException(401, "license_verify_failed") from exc
    jti = payload.get("jti")
    if not jti:
        emit_event(
            request,
            action="me.account.auth",
            outcome="denied",
            reason="missing_jti",
        )
        raise HTTPException(401, "Token missing jti")
    return jti


def _issue_delete_token(jti: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=DELETE_TOKEN_TTL_HOURS)).timestamp()),
        "scope": "account.delete",
    }
    return pyjwt.encode(payload, settings.delete_confirm_jwt_secret, algorithm="HS256")


def _verify_delete_token(token: str, request: Optional[Request] = None) -> str:
    try:
        payload = pyjwt.decode(
            token,
            settings.delete_confirm_jwt_secret,
            algorithms=["HS256"],
        )
    except pyjwt.ExpiredSignatureError as exc:
        emit_event(
            request,
            action="me.account.delete_token",
            outcome="denied",
            reason="expired",
        )
        raise HTTPException(400, "delete_token_expired") from exc
    except pyjwt.InvalidTokenError as exc:
        emit_event(
            request,
            action="me.account.delete_token",
            outcome="denied",
            reason="invalid",
        )
        raise HTTPException(400, "delete_token_invalid") from exc
    if payload.get("scope") != "account.delete":
        emit_event(
            request,
            action="me.account.delete_token",
            outcome="denied",
            reason="wrong_scope",
        )
        raise HTTPException(400, "delete_token_wrong_scope")
    sub = payload.get("sub")
    if not sub:
        emit_event(
            request,
            action="me.account.delete_token",
            outcome="denied",
            reason="missing_sub",
        )
        raise HTTPException(400, "delete_token_missing_sub")
    return str(sub)


class DeleteConfirmBody(BaseModel):
    token: str


@router.post("/delete-request")
async def delete_request(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Step 1: issue a 24h confirm token + email it to the customer.

    The token never appears in the HTTP response.
    In production the SMTP path is mandatory; the response body only
    confirms that an email was dispatched. Dev/test environments fall
    back to the console logger (sender.py ``_send_html``).
    """
    jti = _verify_bearer_license(authorization, request)

    if settings.env == "prod" and not settings.smtp_host:
        emit_event(
            request,
            action="me.account.delete_request",
            outcome="error",
            reason="smtp_not_configured",
        )
        raise HTTPException(503, "deletion_flow_requires_smtp_in_production")

    token = _issue_delete_token(jti)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=DELETE_TOKEN_TTL_HOURS)

    customer_email = ""
    preferred_lang = "en"
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        if row is not None:
            customer_email = row.customer_email or ""
            preferred_lang = row.preferred_lang or "en"

    if customer_email:
        send_account_delete_email(
            to=customer_email,
            license_jti=jti,
            confirm_url=_confirm_url(token),
            expires_at=expires_at.isoformat(),
            lang=preferred_lang,
        )

    log_customer_action(
        license_jti=jti,
        action="account.delete_requested",
        resource=jti,
    )
    emit_event(
        request,
        action="me.account.delete_requested",
        outcome="success",
        user_id=jti,
    )
    response: dict = {
        "ok": True,
        "status": "email_sent",
        "expires_at": expires_at.isoformat(),
        "expires_in_hours": DELETE_TOKEN_TTL_HOURS,
    }
    # Production NEVER returns the token in the
    # response body (it leaks through access logs / APM trace storage).
    # Dev / test (``env != "prod"``) keep the token in the body so
    # operators and the unit-test harness can exercise the flow without
    # an SMTP capture.
    if settings.env != "prod":
        response["confirm_token"] = token
    return response


@router.get("/deletion-status")
async def deletion_status(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """surface the 30-day grace window to the UI.

    Returned shape (always 200):
      - status: "none" | "scheduled" | "purged"
      - scheduled_delete_at / purged_at: ISO strings or null
      - days_remaining: int >= 0 (only relevant when scheduled)
    """
    jti = _verify_bearer_license(authorization, request)
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        if row is None:
            raise HTTPException(404, "license_not_found")
        if row.purged_at is not None:
            return {
                "status": "purged",
                "scheduled_delete_at": None,
                "purged_at": row.purged_at.isoformat(),
                "days_remaining": 0,
            }
        if row.scheduled_delete_at is None:
            return {
                "status": "none",
                "scheduled_delete_at": None,
                "purged_at": None,
                "days_remaining": 0,
            }
        scheduled = row.scheduled_delete_at
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        remaining = max(
            0, int((scheduled - datetime.now(timezone.utc)).total_seconds() // 86400)
        )
        return {
            "status": "scheduled",
            "scheduled_delete_at": scheduled.isoformat(),
            "purged_at": None,
            "days_remaining": remaining,
        }


@router.post("/delete-confirm")
async def delete_confirm(
    body: DeleteConfirmBody,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Step 2: schedule actual purge T+30d."""
    jti = _verify_bearer_license(authorization, request)
    token_jti = _verify_delete_token(body.token, request)
    if token_jti != jti:
        emit_event(
            request,
            action="me.account.delete_confirm",
            outcome="denied",
            reason="token_jti_mismatch",
        )
        raise HTTPException(403, "token_jti_mismatch")
    scheduled = datetime.now(timezone.utc) + timedelta(days=GRACE_DAYS)
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        if row is None:
            emit_event(
                request,
                action="me.account.delete_confirm",
                outcome="denied",
                reason="license_not_found",
            )
            raise HTTPException(404, "license_not_found")
        row.scheduled_delete_at = scheduled
        db.add(row)
        db.commit()
    log_customer_action(
        license_jti=jti,
        action="account.delete_scheduled",
        resource=jti,
        detail=f"purge_at={scheduled.isoformat()}",
    )
    emit_event(
        request,
        action="me.account.delete_confirmed",
        outcome="success",
        user_id=jti,
    )
    return {"ok": True, "scheduled_delete_at": scheduled.isoformat()}


@router.post("/delete-cancel")
async def delete_cancel(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Cancel a pending deletion (only valid before purge has run)."""
    jti = _verify_bearer_license(authorization, request)
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        if row is None:
            emit_event(
                request,
                action="me.account.delete_cancel",
                outcome="denied",
                reason="license_not_found",
            )
            raise HTTPException(404, "license_not_found")
        if row.purged_at is not None:
            emit_event(
                request,
                action="me.account.delete_cancel",
                outcome="denied",
                reason="already_purged",
            )
            raise HTTPException(410, "already_purged")
        row.scheduled_delete_at = None
        db.add(row)
        db.commit()
    log_customer_action(
        license_jti=jti,
        action="account.delete_cancelled",
        resource=jti,
    )
    emit_event(
        request,
        action="me.account.delete_cancelled",
        outcome="success",
        user_id=jti,
    )
    return {"ok": True}
