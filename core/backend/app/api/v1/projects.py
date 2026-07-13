# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-005 — `/v1/projects/{project_id}` MCP gateway endpoint.

Acceptance criteria:
- Invalid JWT → 401
- Tenant mismatch / role insufficient → 403
- Authorized → 200 with project payload
- p95 < 100ms (excluding the upstream PDP cold-start cost)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from cerbos.sdk.client import CerbosClient
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.deps import AuthContext, get_auth_context, get_cerbos_client
from app.auth.cerbos_client import (
    CerbosUnavailable,
    build_resource,
    is_allowed_or_raise,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["mcp-gateway"])


def _load_project(project_id: str) -> dict[str, Any] | None:
    """The caller's real project, from the `projects` table.

    This endpoint used to answer from a hardcoded dict of three — Alice's
    Project, Bob's Project, Carol's Project, in tenants named tenant-1 and
    tenant-2 — left behind by the sprint that was going to replace it. A customer
    asking for their own project got a 404; anyone asking for `proj-t1-alice` got
    a 200 and a Cerbos check performed against invented tenant and owner fields.
    Projects have had a real table for months.
    """
    from sqlmodel import Session, select

    from app.db.session import get_engine
    from app.db.tenant_models import Project

    with Session(get_engine()) as db:
        row = db.exec(
            select(Project).where(
                Project.slug == project_id,
                Project.archived_at.is_(None),  # type: ignore[union-attr]
            )
        ).first()
    if row is None:
        return None
    return {
        "id": row.slug,
        "name": row.name,
        "tenant_id": row.tenant_slug,
        "owner_id": row.owner_subject,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/projects/{project_id}")
def read_project(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    cerbos: CerbosClient = Depends(get_cerbos_client),
) -> dict[str, Any]:
    record = _load_project(project_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="project_not_found")

    principal = auth.as_principal()
    resource = build_resource(
        record["id"],
        "project",
        tenant_id=record["tenant_id"],
        owner_id=record["owner_id"],
    )
    try:
        allowed = is_allowed_or_raise(principal, resource, "read", client=cerbos)
    except CerbosUnavailable as exc:
        # Sprint 2I UAT-046 — PDP transport blip surfaces as 503 so the
        # client retries; falling back to 403 would tell a legitimate
        # user "permanently forbidden" for what is actually an
        # infrastructure outage.
        logger.error(
            "cerbos_unavailable subject=%s project=%s err=%s",
            auth.subject,
            project_id,
            exc,
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authorization_service_unavailable",
            headers={"Retry-After": "30"},
        )
    if not allowed:
        logger.info(
            "project_read_denied subject=%s tenant=%s project=%s",
            auth.subject,
            auth.tenant_id,
            project_id,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")

    return {
        **record,
        "served_at": datetime.now(timezone.utc).isoformat(),
        "principal": auth.subject,
    }
