# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/connectors — Connector Marketplace (catalog + per-tenant connect + real sync)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.connectors import connect, disconnect, list_connectors
from app.connectors.service import connector_fields, sync

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])


def _tenant(auth: AuthContext) -> str:
    return (auth.tenant_id or "default").strip() or "default"


class ConnectRequest(BaseModel):
    credentials: dict = Field(default_factory=dict)


@router.get("")
async def list_connectors_endpoint(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return list_connectors(tenant_slug=_tenant(auth))


@router.get("/{connector_id}/fields")
async def connector_fields_endpoint(
    connector_id: str,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    fields = connector_fields(connector_id)
    if fields is None:
        raise HTTPException(404, "connector_not_found")
    return fields


@router.post("/{connector_id}/connect")
async def connect_endpoint(
    connector_id: str,
    body: ConnectRequest | None = None,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    row = await connect(
        tenant_slug=_tenant(auth), connector_id=connector_id,
        credentials=(body.credentials if body else {}),
    )
    if row is None:
        raise HTTPException(404, "connector_not_found")
    return row


@router.post("/{connector_id}/sync")
async def sync_endpoint(
    connector_id: str,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return await sync(tenant_slug=_tenant(auth), connector_id=connector_id)


@router.post("/{connector_id}/disconnect")
async def disconnect_endpoint(
    connector_id: str,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    row = disconnect(tenant_slug=_tenant(auth), connector_id=connector_id)
    if row is None:
        raise HTTPException(404, "connector_not_found")
    return row
