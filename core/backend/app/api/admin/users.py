# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Q8.5 finalize / Sprint 2B BUG-36 — Admin user + invite management.

GET    /v1/admin/users                    — list users for current tenant
POST   /v1/admin/users/invite             — create invite + magic-link email
GET    /v1/admin/users/invites            — list invites (pending|accepted)
DELETE /v1/admin/users/invite/{invite_id} — revoke pending invite
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.api.admin.auth import admin_required
from app.observability.audit import emit_event

router = APIRouter(prefix="/v1/admin/users", tags=["admin"])
logger = logging.getLogger(__name__)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _resolve_tenant(admin: dict) -> str:
    """Sprint 2B BUG-36 — admin invite is tenant-scoped. Reuse the same
    resolution chain marketplace already ships so bootstrap admins
    aren't silently bound to ``"default"``.
    """
    from app.api.marketplace import _resolve_admin_tenant

    return _resolve_admin_tenant(admin)


@router.get("")
async def list_users(_admin: dict = Depends(admin_required)) -> dict:
    from sqlmodel import Session, select

    from app.db.models import User
    from app.db.session import get_engine

    rows: list[dict] = []
    with Session(get_engine()) as session:
        users = session.exec(select(User).order_by(User.created_at.desc())).all()
        for u in users:
            rows.append(
                {
                    "id": u.id,
                    "email": u.email,
                    "role": u.role,
                    "status": u.status,
                    "tenant_slug": u.tenant_slug,
                    "last_login": _iso(u.claimed_at),
                    "created_at": _iso(u.created_at),
                }
            )

    return {"users": rows, "total": len(rows)}


# ---------- Sprint 2B BUG-36 — invite flow ---------------------------------


class InviteBody(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "operator", "viewer"] = Field(
        default="member"
    )


def _invite_to_dict(row) -> dict:
    return {
        "invite_id": row.invite_id,
        "email": row.email,
        "role": row.role,
        "tenant_id": row.tenant_id,
        "invited_by": row.invited_by,
        "status": row.status,
        "expires_at": _iso(row.expires_at),
        "accepted_at": _iso(row.accepted_at),
        "revoked_at": _iso(row.revoked_at),
        "created_at": _iso(row.created_at),
    }


@router.post("/invite", status_code=201)
async def create_invite(
    body: InviteBody, request: Request, admin: dict = Depends(admin_required)
) -> dict:
    """Create a pending invite + email a magic-link to the recipient."""
    from sqlmodel import Session, select

    from app.auth.magic_link import create_magic_link_token
    from app.config import settings
    from app.db.models import TenantInvite
    from app.db.session import get_engine
    from app.email.sender import send_invite_email

    tenant_id = _resolve_tenant(admin)
    invited_by = admin.get("sub", "admin")

    with Session(get_engine()) as session:
        existing = session.exec(
            select(TenantInvite).where(
                TenantInvite.tenant_id == tenant_id,
                TenantInvite.email == body.email,
                TenantInvite.status == "pending",
            )
        ).first()
        if existing is not None:
            emit_event(
                request,
                action="admin.user.invited",
                outcome="denied",
                reason="duplicate_pending_invite",
                tenant_id=tenant_id,
                resource_id=existing.invite_id,
                status_code=409,
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_pending_invite",
                    "invite_id": existing.invite_id,
                },
            )

        plaintext, digest, expires_at = create_magic_link_token(
            body.email, tenant_id, purpose="invite"
        )
        invite = TenantInvite(
            invite_id=uuid.uuid4().hex[:16],
            email=body.email,
            role=body.role,
            tenant_id=tenant_id,
            invited_by=invited_by,
            magic_token_hash=digest,
            expires_at=expires_at,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        session.add(invite)
        session.commit()
        session.refresh(invite)

    public_host = (settings.public_hostname or "").rstrip("/")
    magic_url = f"{public_host}/auth/magic?token={plaintext}"

    try:
        send_invite_email(
            to=body.email,
            tenant_name=tenant_id,
            role=body.role,
            magic_url=magic_url,
            invited_by=invited_by,
        )
    except Exception as exc:
        logger.warning("invite email send raised: %s", exc)

    emit_event(
        request,
        action="admin.user.invited",
        outcome="success",
        tenant_id=tenant_id,
        resource_id=invite.invite_id,
    )

    return {
        "invite_id": invite.invite_id,
        "email": invite.email,
        "role": invite.role,
        "tenant_id": invite.tenant_id,
        "expires_at": _iso(invite.expires_at),
        "status": invite.status,
    }


@router.get("/invites")
async def list_invites(admin: dict = Depends(admin_required)) -> dict:
    from sqlmodel import Session, select

    from app.db.models import TenantInvite
    from app.db.session import get_engine

    tenant_id = _resolve_tenant(admin)
    rows: list[dict] = []
    with Session(get_engine()) as session:
        results = session.exec(
            select(TenantInvite)
            .where(TenantInvite.tenant_id == tenant_id)
            .where(TenantInvite.status.in_(["pending", "accepted"]))  # type: ignore[union-attr]
            .order_by(TenantInvite.created_at.desc())
        ).all()
        for inv in results:
            rows.append(_invite_to_dict(inv))
    return {"invites": rows, "total": len(rows)}


@router.delete("/invite/{invite_id}", status_code=204)
async def revoke_invite(
    invite_id: str, request: Request, admin: dict = Depends(admin_required)
):
    from fastapi.responses import Response
    from sqlmodel import Session, select

    from app.db.models import TenantInvite
    from app.db.session import get_engine

    tenant_id = _resolve_tenant(admin)
    with Session(get_engine()) as session:
        row = session.exec(
            select(TenantInvite).where(
                TenantInvite.invite_id == invite_id,
                TenantInvite.tenant_id == tenant_id,
            )
        ).first()
        if row is None:
            emit_event(
                request,
                action="admin.user.invite_revoked",
                outcome="denied",
                reason="invite_not_found",
                tenant_id=tenant_id,
                resource_id=invite_id,
                status_code=404,
            )
            raise HTTPException(404, "invite_not_found")
        if row.status != "pending":
            emit_event(
                request,
                action="admin.user.invite_revoked",
                outcome="denied",
                reason=f"invite_status_{row.status}",
                tenant_id=tenant_id,
                resource_id=invite_id,
                status_code=409,
            )
            raise HTTPException(409, f"invite_status_{row.status}")

        row.status = "revoked"
        row.revoked_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()

    emit_event(
        request,
        action="admin.user.invite_revoked",
        outcome="success",
        tenant_id=tenant_id,
        resource_id=invite_id,
    )
    return Response(status_code=204)
