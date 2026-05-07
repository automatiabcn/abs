# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""031 Modul E — Beta admin queue + approve/reject (Bearer admin).

GET    /v1/admin/beta/queue?status=pending
POST   /v1/admin/beta/{request_id}/approve
POST   /v1/admin/beta/{request_id}/reject  body: {reason}
"""

from __future__ import annotations

import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import settings
from app.db.models import BetaRequest, License
from app.db.session import get_engine
from app.licensing import generate_license
from app.observability.audit import emit_event  # Q12-L23 sweep 4

router = APIRouter(prefix="/v1/admin/beta", tags=["admin"])
logger = logging.getLogger(__name__)


def _require_admin(
    authorization: Optional[str], request: Optional[Request] = None
) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        emit_event(
            request,
            action="admin.beta.gate",
            outcome="denied",
            reason="missing_bearer",
            status_code=401,
        )
        raise HTTPException(401, "admin_bearer_required")
    token = authorization.split(None, 1)[1].strip()
    expected = settings.beta_admin_token or ""
    if not expected or not hmac.compare_digest(token, expected):
        emit_event(
            request,
            action="admin.beta.gate",
            outcome="denied",
            reason="admin_token_invalid",
            status_code=403,
        )
        raise HTTPException(403, "admin_token_invalid")


def admin_dep(
    request: Request, authorization: Optional[str] = Header(default=None)
) -> None:
    _require_admin(authorization, request)


class RejectBody(BaseModel):
    reason: str = Field(default="", max_length=512)


def _serialize(row: BetaRequest) -> dict:
    return {
        "id": row.id,
        "email": row.email,
        "name": row.name,
        "company": row.company,
        "use_case": row.use_case,
        "lang": row.lang,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
        "rejected_reason": row.rejected_reason,
        "license_jti": row.license_jti,
    }


@router.get("/queue")
async def list_queue(
    request: Request,
    status: str = "pending",
    limit: int = 100,
    _admin: None = Depends(admin_dep),
) -> dict:
    if status not in {"pending", "approved", "rejected", "all"}:
        emit_event(
            request,
            action="admin.beta.queue",
            outcome="denied",
            reason="invalid_status_filter",
            status_code=400,
        )
        raise HTTPException(400, "invalid_status_filter")
    with Session(get_engine()) as db:
        stmt = select(BetaRequest).order_by(BetaRequest.created_at.desc())  # type: ignore[union-attr]
        if status != "all":
            stmt = stmt.where(BetaRequest.status == status)
        stmt = stmt.limit(min(limit, 500))
        rows = list(db.scalars(stmt).all())
    return {"status": status, "count": len(rows), "items": [_serialize(r) for r in rows]}


@router.post("/{request_id}/approve")
async def approve_request(
    request_id: int,
    request: Request,
    _admin: None = Depends(admin_dep),
) -> dict:
    import jwt as pyjwt

    with Session(get_engine()) as db:
        row = db.scalars(
            select(BetaRequest).where(BetaRequest.id == request_id)
        ).first()
        if row is None:
            emit_event(
                request,
                action="admin.beta.approve",
                outcome="denied",
                reason="request_not_found",
                status_code=404,
                resource_id=str(request_id),
            )
            raise HTTPException(404, "request_not_found")
        if row.status == "approved" and row.license_jti:
            return {"ok": True, "already_approved": True, "license_jti": row.license_jti}
        if row.status == "rejected":
            emit_event(
                request,
                action="admin.beta.approve",
                outcome="denied",
                reason="request_already_rejected",
                status_code=409,
                resource_id=str(request_id),
            )
            raise HTTPException(409, "request_already_rejected")

        token = generate_license(row.email, tier="beta", valid_days=30)
        jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
        now = datetime.now(timezone.utc)
        db.add(
            License(
                jti=jti,
                customer_email=row.email,
                tier="beta",
                seat_count=1,
                issued_at=now,
                expires_at=now + timedelta(days=30),
                preferred_lang=row.lang,
            )
        )
        row.status = "approved"
        row.approved_at = now
        row.license_jti = jti
        db.add(row)
        # Capture email BEFORE commit/session-exit — post-commit `row` is
        # detached and ORM lazy-load raises DetachedInstanceError. The
        # downstream beta_sequence + discord callbacks plus the audit
        # emit all need the email; reading once and reusing the local is
        # also cheaper than re-querying.
        row_email = row.email
        db.commit()

    try:
        from app.email.beta_sequence import schedule_beta_sequence

        schedule_beta_sequence(license_jti=jti, customer_email=row_email)
    except Exception as exc:
        logger.warning("beta_sequence schedule failed: %s", exc)

    try:
        from app.integrations import discord_webhook as dw

        if hasattr(dw, "notify_beta_approved"):
            dw.notify_beta_approved(license_jti=jti, email=row_email)
    except Exception as exc:
        logger.info("discord notify_beta_approved failed: %s", exc)

    emit_event(
        request,
        action="admin.beta.approve",
        outcome="success",
        resource_id=str(request_id),
        email_hint=(row_email or "")[:3],
    )
    return {"ok": True, "request_id": request_id, "license_jti": jti}


@router.post("/{request_id}/reject")
async def reject_request(
    request_id: int,
    body: RejectBody,
    request: Request,
    _admin: None = Depends(admin_dep),
) -> dict:
    with Session(get_engine()) as db:
        row = db.scalars(
            select(BetaRequest).where(BetaRequest.id == request_id)
        ).first()
        if row is None:
            emit_event(
                request,
                action="admin.beta.reject",
                outcome="denied",
                reason="request_not_found",
                status_code=404,
                resource_id=str(request_id),
            )
            raise HTTPException(404, "request_not_found")
        if row.status == "approved":
            emit_event(
                request,
                action="admin.beta.reject",
                outcome="denied",
                reason="request_already_approved",
                status_code=409,
                resource_id=str(request_id),
            )
            raise HTTPException(409, "request_already_approved")
        row.status = "rejected"
        row.rejected_at = datetime.now(timezone.utc)
        row.rejected_reason = body.reason or None
        db.add(row)
        # Same detach trap as approve_request — capture before commit.
        row_email = row.email
        db.commit()
    emit_event(
        request,
        action="admin.beta.reject",
        outcome="success",
        resource_id=str(request_id),
        email_hint=(row_email or "")[:3],
    )
    return {"ok": True, "request_id": request_id, "status": "rejected"}
