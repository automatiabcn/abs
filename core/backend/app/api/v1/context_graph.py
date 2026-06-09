# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/context-graph — Growth Context Graph view + entity resolution run."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.graph_context import context_graph_view, resolve_companies

router = APIRouter(prefix="/v1/context-graph", tags=["context-graph"])


def _tenant(auth: AuthContext) -> str:
    return (auth.tenant_id or "default").strip() or "default"


@router.get("")
async def get_graph(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return context_graph_view(tenant_slug=_tenant(auth))


@router.post("/resolve")
async def run_entity_resolution(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    """Merge duplicate firm records into canonical entities (Turkish-aware)."""
    return resolve_companies(tenant_slug=_tenant(auth))
