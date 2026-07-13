# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Active-project resolution (multi-tenant Phase 1, B4).

A user can belong to multiple projects; the active one is selected per request
via the ``X-Project-Id`` header. This helper resolves + authorizes it:

  * header absent            → None (tenant-wide behaviour, unchanged/legacy)
  * project not in tenant    → 404
  * caller not a member      → 403  (admins bypass membership within their tenant)

When a project is active, RAG ingest stamps ``project_id`` into the chunk
payload and query adds a ``project_id`` filter, giving per-project isolation
ADDITIVELY — documents ingested without a project keep working under plain
tenant scoping (no migration of the live corpus required).
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from fastapi import HTTPException, Request, status
from sqlmodel import Session, select

from app.db.session import get_engine
from app.db.tenant_models import Project
from app.multitenant import project_members as pm

logger = logging.getLogger(__name__)

PROJECT_HEADER = "X-Project-Id"


def resolve_active_project(
    request: Request,
    *,
    tenant_slug: str,
    subject: str,
    roles: Sequence[str] = (),
) -> Optional[str]:
    """Return the authorized active project slug, or None when no header is set."""
    pid = (request.headers.get(PROJECT_HEADER) or "").strip()
    if not pid:
        return None
    tenant = (tenant_slug or "").strip()
    with Session(get_engine()) as db:
        proj = db.exec(
            select(Project).where(
                Project.slug == pid,
                Project.tenant_slug == tenant,
                Project.archived_at == None,  # noqa: E711
            )
        ).first()
    if proj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project_not_found")
    # Admins act tenant-wide; everyone else must be a live member.
    if "admin" not in {r.lower() for r in (roles or [])}:
        if (
            pm.get_role(tenant_slug=tenant, project_slug=pid, user_subject=subject)
            is None
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not_a_project_member")
    return pid
