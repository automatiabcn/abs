# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""N-N user↔project membership store (multi-tenant Phase 1, data layer).

A user can belong to multiple projects (founder decision). Roles:
owner | editor | viewer. Additive + opt-in: no request path enforces these yet;
a later round wires an active-project selector + access checks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.db.session import get_engine
from app.db.tenant_models import ProjectMember

logger = logging.getLogger(__name__)

ROLE_OWNER = "owner"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"
_VALID_ROLES = frozenset({ROLE_OWNER, ROLE_EDITOR, ROLE_VIEWER})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def add_member(
    *, tenant_slug: str, project_slug: str, user_subject: str, role: str = ROLE_VIEWER
) -> ProjectMember:
    """Add or re-activate a user's membership in a project (idempotent upsert)."""
    tenant_slug = (tenant_slug or "").strip()
    project_slug = (project_slug or "").strip()
    user_subject = (user_subject or "").strip()
    role = (role or ROLE_VIEWER).strip()
    if not tenant_slug or not project_slug or not user_subject:
        raise ValueError("tenant_slug, project_slug and user_subject are required")
    if role not in _VALID_ROLES:
        raise ValueError(f"invalid role: {role}")

    with Session(get_engine()) as db:
        row = db.exec(
            select(ProjectMember).where(
                ProjectMember.tenant_slug == tenant_slug,
                ProjectMember.project_slug == project_slug,
                ProjectMember.user_subject == user_subject,
            )
        ).first()
        if row is None:
            row = ProjectMember(
                tenant_slug=tenant_slug,
                project_slug=project_slug,
                user_subject=user_subject,
                role=role,
                granted_at=_now(),
            )
        else:
            row.role = role
            row.revoked_at = None
        db.add(row)
        db.commit()
        db.refresh(row)
    logger.info(
        "project_member add tenant=%s project=%s user=%s role=%s",
        tenant_slug,
        project_slug,
        user_subject,
        role,
    )
    return row


def remove_member(*, tenant_slug: str, project_slug: str, user_subject: str) -> bool:
    """Soft-revoke a membership (keeps the row for audit)."""
    with Session(get_engine()) as db:
        row = db.exec(
            select(ProjectMember).where(
                ProjectMember.tenant_slug == tenant_slug,
                ProjectMember.project_slug == project_slug,
                ProjectMember.user_subject == user_subject,
                ProjectMember.revoked_at.is_(None),  # type: ignore[union-attr]
            )
        ).first()
        if row is None:
            return False
        row.revoked_at = _now()
        db.add(row)
        db.commit()
    return True


def get_role(
    *, tenant_slug: str, project_slug: str, user_subject: str
) -> Optional[str]:
    """Active role of a user in a project, or None if not a (live) member."""
    with Session(get_engine()) as db:
        row = db.exec(
            select(ProjectMember).where(
                ProjectMember.tenant_slug == tenant_slug,
                ProjectMember.project_slug == project_slug,
                ProjectMember.user_subject == user_subject,
                ProjectMember.revoked_at.is_(None),  # type: ignore[union-attr]
            )
        ).first()
        return row.role if row else None


def list_projects_for_user(*, tenant_slug: str, user_subject: str) -> list[dict]:
    """Active project memberships for a user within a tenant."""
    with Session(get_engine()) as db:
        rows = db.exec(
            select(ProjectMember).where(
                ProjectMember.tenant_slug == tenant_slug,
                ProjectMember.user_subject == user_subject,
                ProjectMember.revoked_at.is_(None),  # type: ignore[union-attr]
            )
        ).all()
    return [{"project_slug": r.project_slug, "role": r.role} for r in rows]


def list_members_for_project(*, tenant_slug: str, project_slug: str) -> list[dict]:
    """Active members of a project."""
    with Session(get_engine()) as db:
        rows = db.exec(
            select(ProjectMember).where(
                ProjectMember.tenant_slug == tenant_slug,
                ProjectMember.project_slug == project_slug,
                ProjectMember.revoked_at.is_(None),  # type: ignore[union-attr]
            )
        ).all()
    return [{"user_subject": r.user_subject, "role": r.role} for r in rows]
