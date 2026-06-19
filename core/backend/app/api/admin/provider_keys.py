# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Per-owner provider key management (multi-tenant Phase 1).

Lets an admin store/list/delete provider API keys scoped to an owner —
``user`` (a teammate's own key), ``project`` (a workspace key), or ``org``
(tenant-wide). Keys are encrypted at rest (app.multitenant.crypto) and resolved
at request time project → user → org → global by app.multitenant.provider_keys.

This is the management surface for the BYOK model — each user brings their own
key. Tenant-scoped: a caller only ever touches their own tenant's
rows. Plaintext is never returned.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.admin.auth import admin_required
from app.multitenant import provider_keys as pk
from app.providers.cascade import SETTINGS_KEY_ATTR


def _resolve_admin_tenant(admin: dict) -> str:
    """Resolve the admin's tenant the SAME way the runtime RAG/cascade path does
    (`auth.tenant_id` ← `_resolve_tenant`). Using the marketplace resolver here
    diverged (domain heuristic → a per-domain slug) from the runtime tenant ("default"
    where the data lives), so panel-stored keys/projects were never found at
    request time. Aligning both ends keeps BYOK + project scoping consistent."""
    from app.api.chat import _resolve_tenant

    return _resolve_tenant(str(admin.get("sub") or admin.get("email") or "")) or "default"

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin/provider-keys", tags=["admin", "provider-keys"])

_VALID_PROVIDERS = frozenset(SETTINGS_KEY_ATTR.keys())


def _admin_subject(admin: dict) -> str:
    return str(admin.get("sub") or admin.get("email") or "").strip()


class ProviderKeyIn(BaseModel):
    provider: str = Field(..., min_length=2, max_length=32)
    value: str = Field(..., min_length=4, max_length=8192)
    owner_type: str = Field(default=pk.OWNER_USER)  # user | project | org
    # For owner_type=user, defaults to the calling admin's own subject; for org,
    # defaults to the tenant slug. Required for project.
    owner_id: str | None = Field(default=None, max_length=128)


class ProviderKeyDel(BaseModel):
    provider: str = Field(..., min_length=2, max_length=32)
    owner_type: str = Field(default=pk.OWNER_USER)
    owner_id: str | None = Field(default=None, max_length=128)


def _resolve_owner(admin: dict, tenant: str, owner_type: str, owner_id: str | None) -> str:
    owner_type = (owner_type or "").strip()
    if owner_type == pk.OWNER_ORG:
        return tenant
    if owner_type == pk.OWNER_USER:
        return (owner_id or "").strip() or _admin_subject(admin)
    if owner_type == pk.OWNER_PROJECT:
        oid = (owner_id or "").strip()
        if not oid:
            raise HTTPException(422, "owner_id_required_for_project")
        return oid
    raise HTTPException(422, f"invalid_owner_type: {owner_type}")


@router.get("")
async def list_keys(admin: dict = Depends(admin_required)) -> dict:
    tenant = _resolve_admin_tenant(admin)
    return {"tenant": tenant, "keys": pk.list_provider_keys(tenant_slug=tenant)}


@router.post("")
async def set_key(body: ProviderKeyIn, admin: dict = Depends(admin_required)) -> dict:
    if body.provider not in _VALID_PROVIDERS:
        raise HTTPException(422, f"unknown_provider: {body.provider}")
    tenant = _resolve_admin_tenant(admin)
    owner_id = _resolve_owner(admin, tenant, body.owner_type, body.owner_id)
    try:
        pk.set_provider_key(
            tenant_slug=tenant,
            owner_type=body.owner_type,
            owner_id=owner_id,
            provider=body.provider,
            value=body.value,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    logger.info(
        "provider_key_set tenant=%s owner=%s:%s provider=%s by=%s",
        tenant, body.owner_type, owner_id, body.provider, _admin_subject(admin),
    )
    return {
        "ok": True,
        "owner_type": body.owner_type,
        "owner_id": owner_id,
        "provider": body.provider,
    }


@router.delete("")
async def delete_key(body: ProviderKeyDel, admin: dict = Depends(admin_required)) -> dict:
    tenant = _resolve_admin_tenant(admin)
    owner_id = _resolve_owner(admin, tenant, body.owner_type, body.owner_id)
    removed = pk.delete_provider_key(
        tenant_slug=tenant,
        owner_type=body.owner_type,
        owner_id=owner_id,
        provider=body.provider,
    )
    return {"ok": removed, "deleted": removed}
