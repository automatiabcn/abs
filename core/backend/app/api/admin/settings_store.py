# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Generic per-tenant settings store for the /admin/settings tabs.

Closes the dead-Save-button gap on the Webhooks / Alerts / Security tabs:
``GET/PUT /v1/admin/settings/{section}`` persists + reloads a JSON blob per
(tenant, section). Tenant-scoped via the admin's resolved tenant. Generic so a
new section needs no schema/route change.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.admin.auth import admin_required
from app.api.marketplace import _resolve_admin_tenant
from app.db.session import get_engine
from app.db.tenant_models import TenantSetting

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/admin/settings", tags=["admin", "settings"])

# Allow-list keeps the store bounded + auditable (no arbitrary section spam).
_ALLOWED_SECTIONS = frozenset({"webhooks", "alerts", "security", "general"})
_MAX_BYTES = 16_384


class SettingsBody(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


def _subject(admin: dict) -> str:
    return str(admin.get("sub") or admin.get("email") or "").strip()


def _check_section(section: str) -> str:
    s = (section or "").strip().lower()
    if s not in _ALLOWED_SECTIONS:
        raise HTTPException(404, "unknown_settings_section")
    return s


@router.get("/{section}")
async def get_settings(section: str, admin: dict = Depends(admin_required)) -> dict:
    s = _check_section(section)
    tenant = _resolve_admin_tenant(admin)
    with Session(get_engine()) as db:
        row = db.exec(
            select(TenantSetting).where(
                TenantSetting.tenant_slug == tenant, TenantSetting.section == s
            )
        ).first()
    data: dict[str, Any] = {}
    if row:
        try:
            data = json.loads(row.data_json)
        except (ValueError, TypeError):
            data = {}
    return {"section": s, "data": data}


@router.put("/{section}")
async def put_settings(
    section: str, body: SettingsBody, admin: dict = Depends(admin_required)
) -> dict:
    s = _check_section(section)
    tenant = _resolve_admin_tenant(admin)
    blob = json.dumps(body.data, ensure_ascii=False)
    if len(blob.encode("utf-8")) > _MAX_BYTES:
        raise HTTPException(413, "settings_payload_too_large")
    with Session(get_engine()) as db:
        row = db.exec(
            select(TenantSetting).where(
                TenantSetting.tenant_slug == tenant, TenantSetting.section == s
            )
        ).first()
        if row is None:
            row = TenantSetting(
                tenant_slug=tenant,
                section=s,
                data_json=blob,
                updated_at=datetime.now(timezone.utc),
                updated_by=_subject(admin),
            )
        else:
            row.data_json = blob
            row.updated_at = datetime.now(timezone.utc)
            row.updated_by = _subject(admin)
        db.add(row)
        db.commit()
    logger.info("tenant_settings_saved tenant=%s section=%s", tenant, s)
    return {"ok": True, "section": s, "data": body.data}
