# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/connectors — Connector Marketplace (catalog + per-tenant connect)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.connectors import connect, disconnect, list_connectors

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])


def _tenant(auth: AuthContext) -> str:
    return (auth.tenant_id or "default").strip() or "default"


@router.get("")
async def list_connectors_endpoint(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return list_connectors(tenant_slug=_tenant(auth))


@router.post("/{connector_id}/connect")
async def connect_endpoint(
    connector_id: str,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    row = connect(tenant_slug=_tenant(auth), connector_id=connector_id)
    if row is None:
        raise HTTPException(404, "connector_not_found")
    return row


@router.post("/{connector_id}/disconnect")
async def disconnect_endpoint(
    connector_id: str,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    row = disconnect(tenant_slug=_tenant(auth), connector_id=connector_id)
    if row is None:
        raise HTTPException(404, "connector_not_found")
    return row
