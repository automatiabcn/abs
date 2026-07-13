# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Project CRUD + membership management (multi-tenant Phase 1).

Design decisions:
  * Project creation is restricted to org ``admin`` or ``manager`` (not every
    member).
  * A user can belong to MULTIPLE projects (N-N), with a per-project role
    (owner|editor|viewer) managed here.

Everything is tenant-scoped via the admin's resolved tenant; a caller can only
ever see/modify projects + members within their own tenant.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.admin.auth import admin_required
from app.db.session import get_engine
from app.db.tenant_models import Project
from app.multitenant import project_members as pm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin/projects", tags=["admin", "projects"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,94}$")
_CREATOR_ROLES = frozenset({"admin", "manager"})


def _resolve_admin_tenant(admin: dict) -> str:
    """Runtime-consistent tenant (matches RAG/cascade `auth.tenant_id`), so
    projects live under the same tenant the data + queries use."""
    from app.api.chat import _resolve_tenant

    return (
        _resolve_tenant(str(admin.get("sub") or admin.get("email") or "")) or "default"
    )


def _subject(admin: dict) -> str:
    return str(admin.get("sub") or admin.get("email") or "").strip()


def _require_creator(admin: dict) -> None:
    """Project creation gate — admin or manager only (by design).

    admin_required already enforces admin-level access; bootstrap/admin tokens
    have no explicit role and are allowed. A non-admin principal carrying a
    role claim must be admin or manager."""
    role = str(admin.get("role") or "").strip().lower()
    if role and role not in _CREATOR_ROLES:
        raise HTTPException(403, "project_create_forbidden_for_role")


class ProjectIn(BaseModel):
    slug: str = Field(..., min_length=2, max_length=96)
    name: str = Field(default="", max_length=128)


class MemberIn(BaseModel):
    user_subject: str = Field(..., min_length=1, max_length=128)
    role: str = Field(default="viewer")  # owner | editor | viewer


@router.get("")
async def list_projects(admin: dict = Depends(admin_required)) -> dict:
    tenant = _resolve_admin_tenant(admin)
    with Session(get_engine()) as db:
        rows = db.exec(
            select(Project).where(
                Project.tenant_slug == tenant,
                Project.archived_at == None,  # noqa: E711
            )
        ).all()
    return {
        "tenant": tenant,
        "projects": [
            {
                "slug": p.slug,
                "name": p.name,
                "owner": p.owner_subject,
                "qdrant_collection": p.qdrant_collection,
            }
            for p in rows
        ],
    }


@router.post("")
async def create_project(
    body: ProjectIn, admin: dict = Depends(admin_required)
) -> dict:
    _require_creator(admin)
    tenant = _resolve_admin_tenant(admin)
    slug = body.slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise HTTPException(422, "invalid_slug")
    subject = _subject(admin)
    with Session(get_engine()) as db:
        # Tenant-scoped: a slug taken in another tenant is fine. An ARCHIVED
        # project with the same slug in this tenant is reactivated (the row
        # persists under the per-tenant unique constraint, so we can't insert a
        # duplicate) rather than 409'ing the operator out of reusing the name.
        existing = db.exec(
            select(Project).where(Project.slug == slug, Project.tenant_slug == tenant)
        ).first()
        if existing is not None:
            if existing.archived_at is None:
                raise HTTPException(409, "project_slug_taken")
            existing.archived_at = None
            existing.name = body.name or slug
            existing.owner_subject = subject
            db.add(existing)
            db.commit()
        else:
            db.add(
                Project(
                    slug=slug,
                    tenant_slug=tenant,
                    name=body.name or slug,
                    owner_subject=subject,
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
    # creator becomes project owner
    pm.add_member(
        tenant_slug=tenant,
        project_slug=slug,
        user_subject=subject,
        role=pm.ROLE_OWNER,
    )
    logger.info("project_created tenant=%s slug=%s by=%s", tenant, slug, subject)
    return {"ok": True, "slug": slug, "tenant": tenant}


@router.delete("/{slug}")
async def archive_project(slug: str, admin: dict = Depends(admin_required)) -> dict:
    _require_creator(admin)
    tenant = _resolve_admin_tenant(admin)
    with Session(get_engine()) as db:
        proj = db.exec(
            select(Project).where(Project.slug == slug, Project.tenant_slug == tenant)
        ).first()
        if not proj:
            raise HTTPException(404, "project_not_found")
        proj.archived_at = datetime.now(timezone.utc)
        db.add(proj)
        db.commit()
    return {"ok": True, "slug": slug, "archived": True}


@router.get("/{slug}/members")
async def list_members(slug: str, admin: dict = Depends(admin_required)) -> dict:
    tenant = _resolve_admin_tenant(admin)
    return {
        "project": slug,
        "members": pm.list_members_for_project(tenant_slug=tenant, project_slug=slug),
    }


@router.post("/{slug}/members")
async def add_member(
    slug: str, body: MemberIn, admin: dict = Depends(admin_required)
) -> dict:
    _require_creator(admin)
    tenant = _resolve_admin_tenant(admin)
    with Session(get_engine()) as db:
        if not db.exec(
            select(Project).where(Project.slug == slug, Project.tenant_slug == tenant)
        ).first():
            raise HTTPException(404, "project_not_found")
    try:
        pm.add_member(
            tenant_slug=tenant,
            project_slug=slug,
            user_subject=body.user_subject,
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "ok": True,
        "project": slug,
        "user_subject": body.user_subject,
        "role": body.role,
    }


@router.delete("/{slug}/members/{user_subject}")
async def remove_member(
    slug: str, user_subject: str, admin: dict = Depends(admin_required)
) -> dict:
    _require_creator(admin)
    tenant = _resolve_admin_tenant(admin)
    removed = pm.remove_member(
        tenant_slug=tenant, project_slug=slug, user_subject=user_subject
    )
    return {"ok": removed, "removed": removed}
