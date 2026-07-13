# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Admin API — register & test a tenant's external MCP servers.

ABS connects OUT to these servers as an MCP client and (Slice 2) federates
their tools. Admin-gated + tenant-scoped (same resolver as provider-keys so the
tenant matches the runtime path). Gated behind ``settings.external_mcp_enabled``
— every route 404s when the feature is off, so a deployment opts in explicitly.
Plaintext secrets are accepted on write but NEVER returned.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.admin.auth import admin_required
from app.config import settings
from app.mcp.external import federation, service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin/external-mcp", tags=["admin", "external-mcp"])


def _feature_enabled() -> None:
    if not getattr(settings, "external_mcp_enabled", False):
        raise HTTPException(404, "external_mcp_disabled")


def _resolve_admin_tenant(admin: dict) -> str:
    """Match the runtime tenant the same way provider-keys does."""
    from app.api.chat import _resolve_tenant

    return (
        _resolve_tenant(str(admin.get("sub") or admin.get("email") or "")) or "default"
    )


def _subject(admin: dict) -> str:
    return str(admin.get("sub") or admin.get("email") or "").strip()


class ServerIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    url: str = Field(..., min_length=4, max_length=2048)
    transport: str = Field(default="http")  # http | sse
    auth_type: str = Field(default="none")  # none | bearer | header
    secret: str = Field(default="", max_length=8192)
    header_name: str = Field(default="", max_length=64)


class ServerPatch(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    url: str | None = Field(default=None, max_length=2048)
    transport: str | None = None
    auth_type: str | None = None
    secret: str | None = Field(default=None, max_length=8192)  # None=keep, ""=clear
    header_name: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None


@router.get("")
async def list_servers(admin: dict = Depends(admin_required)) -> dict:
    _feature_enabled()
    tenant = _resolve_admin_tenant(admin)
    return {"tenant": tenant, "servers": service.list_servers(tenant)}


@router.post("", status_code=201)
async def add_server(body: ServerIn, admin: dict = Depends(admin_required)) -> dict:
    _feature_enabled()
    tenant = _resolve_admin_tenant(admin)
    try:
        return service.add_server(
            tenant_slug=tenant,
            name=body.name,
            url=body.url,
            transport=body.transport,
            auth_type=body.auth_type,
            secret=body.secret,
            header_name=body.header_name,
            created_by=_subject(admin),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # SSRF/url validation (ExternalMcpError)
        raise HTTPException(422, str(exc)) from exc


@router.get("/{slug}")
async def get_server(slug: str, admin: dict = Depends(admin_required)) -> dict:
    _feature_enabled()
    tenant = _resolve_admin_tenant(admin)
    row = service.get_server(tenant, slug)
    if not row:
        raise HTTPException(404, "not_found")
    return row


@router.patch("/{slug}")
async def update_server(
    slug: str, body: ServerPatch, admin: dict = Depends(admin_required)
) -> dict:
    _feature_enabled()
    tenant = _resolve_admin_tenant(admin)
    try:
        row = service.update_server(
            tenant_slug=tenant,
            slug=slug,
            name=body.name,
            url=body.url,
            transport=body.transport,
            auth_type=body.auth_type,
            secret=body.secret,
            header_name=body.header_name,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc
    if not row:
        raise HTTPException(404, "not_found")
    # Reflect enable/disable into the /mcp federation immediately.
    if row.get("enabled"):
        await federation.federate_server(tenant, slug)
    else:
        federation.unfederate_server(slug)
    return row


@router.delete("/{slug}", status_code=200)
async def remove_server(slug: str, admin: dict = Depends(admin_required)) -> dict:
    _feature_enabled()
    tenant = _resolve_admin_tenant(admin)
    federation.unfederate_server(slug)
    return {"ok": service.remove_server(tenant, slug)}


@router.post("/{slug}/test")
async def test_server(slug: str, admin: dict = Depends(admin_required)) -> dict:
    _feature_enabled()
    tenant = _resolve_admin_tenant(admin)
    result = await service.test_connection(tenant, slug)
    # A successful test (re)publishes the tools into /mcp when federation is on.
    if result.get("ok"):
        result["federated"] = await federation.federate_server(tenant, slug)
    return result


@router.get("/_status/federation")
async def federation_status(admin: dict = Depends(admin_required)) -> dict:
    _feature_enabled()
    return federation.federated_overview()
