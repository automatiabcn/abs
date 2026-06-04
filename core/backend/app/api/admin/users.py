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


def _active_license_jti() -> str:
    """Best-effort active (non-revoked) license jti, used to tag the
    persistent customer audit trail so user-management actions surface in the
    Denetim (/v1/admin/audit/recent) UI. Pre-fix invite + role/status changes
    only hit ``emit_event`` (structured logs), so they never appeared in the
    admin-visible audit table. Returns "" in dev/pre-license — the audit
    logger then skips silently."""
    try:
        from sqlmodel import Session, select

        from app.db.models import License
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            row = db.exec(
                select(License)
                .where(License.revoked_at == None)  # noqa: E711
                .order_by(License.issued_at.desc())
            ).first()
            return str(row.jti) if row and row.jti else ""
    except Exception:
        return ""


def _audit(action: str, resource: str | None = None, detail: str | None = None) -> None:
    """Best-effort persistent audit write for admin user-management actions.
    Never raises — auditing must not block the action it records."""
    try:
        from app.customer_audit.logger import log_customer_action

        # log_customer_action skips on an empty jti; fall back to a sentinel
        # (mirrors setup.py's "setup-pre-license") so admin user-management
        # actions are ALWAYS auditable, even on a pre-license dev box.
        log_customer_action(
            license_jti=_active_license_jti() or "admin-action",
            action=action,
            resource=resource,
            detail=detail,
        )
    except Exception:  # pragma: no cover — defensive only
        pass


@router.get("")
async def list_users(admin: dict = Depends(admin_required)) -> dict:
    from sqlmodel import Session, select

    from app.db.models import User
    from app.db.session import get_engine

    # Tenant-scope the listing to match invite/list_invites/update_user, which
    # all resolve and enforce the caller's tenant. Pre-fix list_users returned
    # EVERY tenant's users: a cross-tenant email leak, and — because role/status
    # mutation IS tenant-scoped — the panel rendered rows whose role dropdown
    # 404'd on save (the user belonged to another tenant). Single-tenant
    # self-host is unaffected (one tenant → same set).
    tenant_id = _resolve_tenant(admin)
    rows: list[dict] = []
    with Session(get_engine()) as session:
        users = session.exec(
            select(User)
            .where(User.tenant_slug == tenant_id)
            .order_by(User.created_at.desc())
        ).all()
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
    # /activate is the friendly SPA claim page (NOT /auth/magic, which Caddy
    # routes to the backend and would show raw JSON).
    magic_url = f"{public_host}/activate?token={plaintext}"

    # The invite is only usable once the recipient opens the magic link. On a
    # self-host install with no SMTP (the default — settings.smtp_host == "")
    # the email never leaves the box: send_invite_email console-logs and
    # returns, so the link only ever reaches the server stdout. Pre-fix the
    # response also withheld the link, leaving the admin no way to deliver it —
    # the invitee stayed `pending` and every login returned 401. Now we email
    # only when SMTP is configured, and otherwise return the magic_url in the
    # response so the authenticated, tenant-scoped admin can copy it and hand
    # it over manually. (Returning it to the admin is safe: this endpoint is
    # behind admin_required, unlike the anonymous /auth/signup path.)
    email_configured = bool(settings.smtp_host)
    email_sent = False
    if email_configured:
        try:
            send_invite_email(
                to=body.email,
                tenant_name=tenant_id,
                role=body.role,
                magic_url=magic_url,
                invited_by=invited_by,
            )
            email_sent = True
        except Exception as exc:
            logger.warning("invite email send raised: %s", exc)
    else:
        logger.info(
            "invite email skipped (SMTP not configured) — link returned to admin "
            "for manual delivery invite_id=%s",
            invite.invite_id,
        )

    emit_event(
        request,
        action="admin.user.invited",
        outcome="success",
        tenant_id=tenant_id,
        resource_id=invite.invite_id,
        email_sent=email_sent,
    )
    _audit(
        "admin.user.invited",
        resource=invite.email,
        detail=f"role={invite.role} tenant={tenant_id} email_sent={email_sent}",
    )

    resp: dict = {
        "invite_id": invite.invite_id,
        "email": invite.email,
        "role": invite.role,
        "tenant_id": invite.tenant_id,
        "expires_at": _iso(invite.expires_at),
        "status": invite.status,
        "email_sent": email_sent,
    }
    if not email_sent:
        # No email delivery — hand the activation link back so the admin can
        # share it out-of-band. Plaintext token is unrecoverable later (only
        # the HMAC digest is stored), so this is the one chance to copy it.
        resp["magic_url"] = magic_url
        resp["activation_note"] = (
            "SMTP yapılandırılmadığı için davet e-postası gönderilmedi. "
            "Bu aktivasyon bağlantısını kullanıcıya elle iletin (24 saat geçerli)."
        )
    return resp


class UserUpdateBody(BaseModel):
    """Role / status mutation for an existing user row. Both fields are
    optional so the caller can change one without echoing the other."""

    role: Optional[Literal["admin", "operator", "member", "viewer"]] = None
    status: Optional[Literal["active", "revoked"]] = None


def _count_active_admins(session, tenant_slug: str, exclude_id: Optional[int] = None) -> int:
    """How many active `admin`-role users remain in the tenant (optionally
    excluding one row being mutated). Used to block the last-admin lockout."""
    from app.db.models import User

    from sqlmodel import select

    stmt = (
        select(User)
        .where(User.tenant_slug == tenant_slug)
        .where(User.role == "admin")
        .where(User.status == "active")
    )
    rows = session.exec(stmt).all()
    return sum(1 for r in rows if r.id != exclude_id)


@router.patch("/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdateBody,
    request: Request,
    admin: dict = Depends(admin_required),
) -> dict:
    """Change a user's role and/or status.

    Authorization is admin-only (admin_required). Guards prevent an admin
    from locking the tenant out of its own console: the LAST active admin
    cannot be demoted to a lower role nor revoked. Operating across tenants
    is refused — only rows whose tenant_slug matches the caller's are
    mutable.
    """
    from sqlmodel import Session, select

    from app.db.models import User
    from app.db.session import get_engine

    if body.role is None and body.status is None:
        raise HTTPException(400, "no_fields_to_update")

    tenant_id = _resolve_tenant(admin)
    actor_email = admin.get("sub", "")

    with Session(get_engine()) as session:
        user = session.exec(select(User).where(User.id == user_id)).first()
        if user is None:
            emit_event(
                request,
                action="admin.user.updated",
                outcome="denied",
                reason="user_not_found",
                tenant_id=tenant_id,
                resource_id=str(user_id),
                status_code=404,
            )
            raise HTTPException(404, "user_not_found")
        if user.tenant_slug != tenant_id:
            # Cross-tenant mutation — refuse without leaking existence.
            emit_event(
                request,
                action="admin.user.updated",
                outcome="denied",
                reason="cross_tenant",
                tenant_id=tenant_id,
                resource_id=str(user_id),
                status_code=404,
            )
            raise HTTPException(404, "user_not_found")

        # Last-admin lockout guard. If this row is the final active admin and
        # the change would strip its admin powers (role away from admin, or
        # revoke), refuse so the tenant keeps at least one console owner.
        demotes_admin = (
            user.role == "admin"
            and user.status == "active"
            and (
                (body.role is not None and body.role != "admin")
                or body.status == "revoked"
            )
        )
        if demotes_admin and _count_active_admins(session, tenant_id, exclude_id=user.id) == 0:
            emit_event(
                request,
                action="admin.user.updated",
                outcome="denied",
                reason="last_admin_protected",
                tenant_id=tenant_id,
                resource_id=str(user_id),
                status_code=409,
            )
            raise HTTPException(
                409,
                {
                    "error": "last_admin_protected",
                    "detail": "Son aktif admin'in yetkisi alınamaz veya iptal edilemez. "
                    "Önce başka bir kullanıcıyı admin yapın.",
                },
            )

        before = {"role": user.role, "status": user.status}
        if body.role is not None:
            user.role = body.role
        if body.status is not None:
            user.status = body.status
        session.add(user)
        session.commit()
        session.refresh(user)
        # Snapshot before the session closes — accessing attributes on a
        # detached instance after the `with` block would raise.
        result = {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "tenant_slug": user.tenant_slug,
        }
        after = {"role": user.role, "status": user.status}

    emit_event(
        request,
        action="admin.user.updated",
        outcome="success",
        tenant_id=tenant_id,
        resource_id=str(user_id),
        actor=actor_email,
        detail=f"{before} -> {after}",
    )
    _audit(
        "admin.user.updated",
        resource=result["email"],
        detail=f"{before} -> {after} by={actor_email}",
    )
    return result


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
    _audit("admin.user.invite_revoked", resource=invite_id, detail=f"tenant={tenant_id}")
    return Response(status_code=204)
