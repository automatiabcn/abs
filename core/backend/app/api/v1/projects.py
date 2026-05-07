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
from app.auth.cerbos_client import build_resource, is_allowed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["mcp-gateway"])


# Stub project store. Replaced by real persistence in T-009 (RAG sprint).
_DEMO_PROJECTS: dict[str, dict[str, Any]] = {
    "proj-t1-alice": {
        "id": "proj-t1-alice",
        "name": "Alice Project",
        "tenant_id": "tenant-1",
        "owner_id": "alice",
        "created_at": "2026-04-27T00:00:00Z",
    },
    "proj-t1-bob": {
        "id": "proj-t1-bob",
        "name": "Bob Project",
        "tenant_id": "tenant-1",
        "owner_id": "bob",
        "created_at": "2026-04-27T00:00:00Z",
    },
    "proj-t2-carol": {
        "id": "proj-t2-carol",
        "name": "Carol Project",
        "tenant_id": "tenant-2",
        "owner_id": "carol",
        "created_at": "2026-04-27T00:00:00Z",
    },
}


@router.get("/projects/{project_id}")
def read_project(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    cerbos: CerbosClient = Depends(get_cerbos_client),
) -> dict[str, Any]:
    record = _DEMO_PROJECTS.get(project_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="project_not_found")

    principal = auth.as_principal()
    resource = build_resource(
        record["id"],
        "project",
        tenant_id=record["tenant_id"],
        owner_id=record["owner_id"],
    )
    if not is_allowed(principal, resource, "read", client=cerbos):
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
