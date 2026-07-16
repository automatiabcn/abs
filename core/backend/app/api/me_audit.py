# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Customer-facing audit log API.

GET /v1/me/audit-log?limit=50&offset=0  (Bearer license_key)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from sqlmodel import Session, select

from app.api.me_auth import panel_session_identity
from app.db.models import CustomerAuditEntry
from app.db.session import get_engine
from app.licensing import verify_license
from app.observability.audit import emit_event

router = APIRouter(prefix="/v1/me", tags=["me"])
logger = logging.getLogger(__name__)


def _verify_bearer_license(
    authorization: Optional[str], request: Optional[Request] = None
) -> str:
    """Bearer = license JWT. Returns jti or raises 401.

    Falls back to the signed-in panel session on a self-host box (see
    me_auth.panel_session_identity) so the operator can read their own log.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        fallback = panel_session_identity(request)
        if fallback is not None:
            emit_event(
                request,
                action="me.audit.auth",
                outcome="success",
                reason="panel_session_fallback",
            )
            return fallback[0]
        emit_event(
            request,
            action="me.audit.auth",
            outcome="denied",
            reason="missing_bearer",
            status_code=401,
        )
        raise HTTPException(401, "Authorization Bearer license required")
    token = authorization.split(None, 1)[1].strip()
    try:
        payload = verify_license(token)
    except HTTPException:
        emit_event(
            request,
            action="me.audit.auth",
            outcome="denied",
            reason="license_invalid",
            status_code=401,
        )
        raise
    except Exception as exc:
        # Same PyJWT internals leak as me_account /
        # me_data_export / me_consent. Generic detail; error_class to
        # audit only.
        emit_event(
            request,
            action="me.audit.auth",
            outcome="error",
            reason="license_verify_exception",
            status_code=401,
            error_class=type(exc).__name__,
        )
        raise HTTPException(401, "license_verify_failed") from exc
    jti = payload.get("jti")
    if not jti:
        emit_event(
            request,
            action="me.audit.auth",
            outcome="denied",
            reason="missing_jti",
            status_code=401,
        )
        raise HTTPException(401, "Token missing jti")
    return jti


@router.get("/audit-log")
async def audit_log(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    action: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Last 90 days of audit entries for the requesting license."""
    jti = _verify_bearer_license(authorization, request)
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    with Session(get_engine()) as db:
        stmt = (
            select(CustomerAuditEntry)
            .where(CustomerAuditEntry.license_jti == jti)
            .where(CustomerAuditEntry.ts >= cutoff)
            .order_by(CustomerAuditEntry.ts.desc())  # type: ignore[union-attr]
            .offset(offset)
            .limit(limit)
        )
        if action:
            stmt = stmt.where(CustomerAuditEntry.action == action)
        rows = list(db.scalars(stmt).all())
    out = []
    for r in rows:
        ts = r.ts
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out.append(
            {
                "id": r.id,
                "ts": ts.isoformat(),
                "action": r.action,
                "resource": r.resource,
                "detail": r.detail,
                "ip_hash": r.ip_hash,
                "user_agent_short": r.user_agent_short,
            }
        )
    return {"license_jti": jti, "count": len(out), "entries": out}
