# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Self-serve tenant provisioning (Multi-tenant Faz0 #3).

When a user claims a public self-signup, they pick a ``tenant_slug`` but no
workspace infrastructure is created — the session carried a dangling tenant.
This module makes the claim actually *provision* that tenant so the new owner
lands on a working workspace:

    Tenant(slug)              — the org row
    Project(slug="default")   — a first project (Qdrant collection scope)
    TenantProject(link)       — tenant ↔ project association
    ProjectMember(owner)      — the signer-upper owns their default project

Everything is an idempotent get-or-create, so:
  • re-claiming / replaying a token never duplicates rows;
  • bootstrapping an already-existing tenant (e.g. an invited user landing in a
    tenant an admin already created) only ensures the membership;
  • single-tenant self-host ("default") is unaffected — calling it for
    "default" simply makes the canonical rows exist (additive, harmless).

Best-effort by contract: callers wrap it so a provisioning hiccup never blocks
account activation. Returns a small summary dict for logging/tests.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict

from sqlmodel import Session, select

from app.db.session import get_engine
from app.db.tenant_models import Project, Tenant, TenantProject

logger = logging.getLogger(__name__)

DEFAULT_PROJECT_SLUG = "default"
DEFAULT_QDRANT_COLLECTION = "abs_documents"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_tenant_provisioned(
    tenant_slug: str, *, owner_subject: str, tenant_name: str = ""
) -> Dict[str, object]:
    """Idempotently ensure a tenant + its default project + the owner's
    membership exist. Safe to call repeatedly and for the "default" tenant.

    Returns ``{tenant, project, created_tenant, created_project, owner}``.
    """
    slug = (tenant_slug or "").strip().lower()
    owner = (owner_subject or "").strip()
    if not slug:
        raise ValueError("tenant_slug is required")

    created_tenant = False
    created_project = False

    with Session(get_engine()) as db:
        tenant = db.exec(select(Tenant).where(Tenant.slug == slug)).first()
        if tenant is None:
            tenant = Tenant(
                slug=slug,
                name=(tenant_name or slug)[:128],
                created_at=_now(),
            )
            db.add(tenant)
            db.commit()
            created_tenant = True

        project = db.exec(
            select(Project).where(
                Project.tenant_slug == slug,
                Project.slug == DEFAULT_PROJECT_SLUG,
            )
        ).first()
        if project is None:
            db.add(
                Project(
                    slug=DEFAULT_PROJECT_SLUG,
                    tenant_slug=slug,
                    name="Default",
                    owner_subject=owner,
                    qdrant_collection=DEFAULT_QDRANT_COLLECTION,
                    created_at=_now(),
                )
            )
            db.commit()
            created_project = True
        elif project.archived_at is not None:
            # Re-activate a previously archived default project rather than
            # leaving the new owner without a workspace.
            project.archived_at = None
            if owner and not project.owner_subject:
                project.owner_subject = owner
            db.add(project)
            db.commit()

        # tenant ↔ project association (idempotent on the active row)
        link = db.exec(
            select(TenantProject).where(
                TenantProject.tenant_slug == slug,
                TenantProject.project_slug == DEFAULT_PROJECT_SLUG,
                TenantProject.revoked_at.is_(None),  # type: ignore[union-attr]
            )
        ).first()
        if link is None:
            db.add(
                TenantProject(
                    tenant_slug=slug,
                    project_slug=DEFAULT_PROJECT_SLUG,
                    role="owner" if owner else "member",
                    granted_at=_now(),
                )
            )
            db.commit()

    # ProjectMember owner — delegated to the shared idempotent upsert so role
    # semantics stay in one place. Only when we have an owner subject.
    if owner:
        try:
            from app.multitenant import project_members as pm

            pm.add_member(
                tenant_slug=slug,
                project_slug=DEFAULT_PROJECT_SLUG,
                user_subject=owner,
                role=pm.ROLE_OWNER,
            )
        except Exception:  # noqa: BLE001 — membership is best-effort
            logger.info("provisioning owner membership skipped", exc_info=True)

    logger.info(
        "tenant_provisioned slug=%s owner=%s created_tenant=%s created_project=%s",
        slug, owner, created_tenant, created_project,
    )
    return {
        "tenant": slug,
        "project": DEFAULT_PROJECT_SLUG,
        "created_tenant": created_tenant,
        "created_project": created_project,
        "owner": owner,
    }
