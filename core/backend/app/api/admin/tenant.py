# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Admin tenant + branding save endpoints."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.admin.auth import admin_required
from app.db.session import get_engine
from app.db.tenant_models import Tenant
from app.observability.audit import emit_event

router = APIRouter(prefix="/v1/admin", tags=["admin", "tenant"])
logger = logging.getLogger(__name__)


_SLUG_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")
_HEX_RX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_BRANDING_MAX = 500
_LOGO_HOST_ALLOWLIST = (
    "automatiabcn.com",
    "abs.automatiabcn.com",
    "cdn.automatiabcn.com",
)


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    slug: Optional[str] = Field(default=None, max_length=64)
    branding_message: Optional[str] = Field(default=None, max_length=_BRANDING_MAX)


class BrandingUpdate(BaseModel):
    logo_url: Optional[str] = Field(default=None, max_length=512)
    primary_color: Optional[str] = Field(default=None, max_length=7)


def _resolve_tenant_slug(admin: dict) -> str:
    from app.api.marketplace import _resolve_admin_tenant

    return _resolve_admin_tenant(admin)


def _validate_logo_url(raw: str) -> None:
    if not raw:
        return
    parsed = urlparse(raw)
    if parsed.scheme != "https":
        raise HTTPException(422, "logo_url_must_be_https")
    host = (parsed.hostname or "").lower()
    if not host:
        raise HTTPException(422, "logo_url_missing_host")
    from app.config import settings as _settings

    own = (_settings.public_hostname or "").lower()
    own_host = urlparse(own).hostname or own
    extra = (own_host,) if own_host else ()
    allowed = _LOGO_HOST_ALLOWLIST + extra
    if host in allowed:
        return
    if any(host.endswith("." + h) for h in allowed):
        return
    raise HTTPException(422, "logo_url_host_not_allowed")


def _tenant_to_dict(t: Tenant) -> dict:
    return {
        "id": t.id,
        "slug": t.slug,
        "name": t.name,
        "branding_message": t.branding_message,
        "logo_url": t.logo_url,
        "primary_color": t.primary_color,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "archived_at": t.archived_at.isoformat() if t.archived_at else None,
    }


def _get_or_create_tenant(slug: str) -> Tenant:
    with Session(get_engine()) as db:
        row = db.exec(select(Tenant).where(Tenant.slug == slug)).first()
        if row is not None:
            return row
        row = Tenant(
            slug=slug,
            name=slug,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


@router.get("/tenant")
async def get_tenant(request: Request, admin: dict = Depends(admin_required)) -> dict:
    slug = _resolve_tenant_slug(admin)
    try:
        tenant = _get_or_create_tenant(slug)
    except Exception as err:
        logger.exception("tenant_get failed for slug=%s err=%s", slug, err)
        emit_event(
            request,
            action="admin.tenant.get",
            outcome="error",
            reason="db_error",
            tenant_id=slug,
            status_code=500,
        )
        raise HTTPException(500, "tenant_lookup_failed") from err
    emit_event(
        request,
        action="admin.tenant.get",
        outcome="success",
        tenant_id=slug,
    )
    return _tenant_to_dict(tenant)


@router.get("/tenant/slug-available")
async def slug_available(
    request: Request,
    slug: str = Query(..., min_length=2, max_length=64),
    admin: dict = Depends(admin_required),
) -> dict:
    if not _SLUG_RX.match(slug):
        return {"slug": slug, "available": False, "reason": "invalid_format"}
    own_slug = _resolve_tenant_slug(admin)
    if slug == own_slug:
        return {"slug": slug, "available": True, "reason": "current"}
    try:
        with Session(get_engine()) as db:
            row = db.exec(select(Tenant).where(Tenant.slug == slug)).first()
    except Exception as err:
        logger.warning("slug_available db error: %s", err)
        return {"slug": slug, "available": False, "reason": "db_error"}
    return {"slug": slug, "available": row is None}


@router.patch("/tenant")
async def update_tenant(
    body: TenantUpdate,
    request: Request,
    admin: dict = Depends(admin_required),
) -> dict:
    slug = _resolve_tenant_slug(admin)
    changes = body.model_dump(exclude_none=True)

    if "slug" in changes:
        new_slug = changes["slug"]
        if not _SLUG_RX.match(new_slug):
            emit_event(
                request,
                action="admin.tenant.update",
                outcome="denied",
                reason="invalid_slug",
                tenant_id=slug,
                status_code=422,
            )
            raise HTTPException(422, "slug_must_match_a-z0-9-")

    if "branding_message" in changes:
        changes["branding_message"] = changes["branding_message"][:_BRANDING_MAX]

    try:
        with Session(get_engine()) as db:
            tenant = db.exec(select(Tenant).where(Tenant.slug == slug)).first()
            if tenant is None:
                tenant = Tenant(
                    slug=slug,
                    name=slug,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(tenant)
                db.flush()
            if "slug" in changes and changes["slug"] != tenant.slug:
                conflict = db.exec(
                    select(Tenant).where(Tenant.slug == changes["slug"])
                ).first()
                if conflict is not None:
                    emit_event(
                        request,
                        action="admin.tenant.update",
                        outcome="denied",
                        reason="slug_taken",
                        tenant_id=slug,
                        status_code=409,
                    )
                    raise HTTPException(409, "slug_taken")
                tenant.slug = changes["slug"]
            if "name" in changes:
                tenant.name = changes["name"]
            if "branding_message" in changes:
                tenant.branding_message = changes["branding_message"]
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("tenant update failed slug=%s err=%s", slug, err)
        emit_event(
            request,
            action="admin.tenant.update",
            outcome="error",
            reason="db_error",
            tenant_id=slug,
            status_code=500,
        )
        raise HTTPException(500, "tenant_update_failed") from err

    emit_event(
        request,
        action="admin.tenant.update",
        outcome="success",
        tenant_id=tenant.slug,
        count=len(changes),
    )
    return _tenant_to_dict(tenant)


@router.patch("/branding")
async def update_branding(
    body: BrandingUpdate,
    request: Request,
    admin: dict = Depends(admin_required),
) -> dict:
    slug = _resolve_tenant_slug(admin)
    changes = body.model_dump(exclude_none=True)

    if "logo_url" in changes:
        try:
            _validate_logo_url(changes["logo_url"])
        except HTTPException as exc:
            emit_event(
                request,
                action="admin.branding.update",
                outcome="denied",
                reason=str(exc.detail),
                tenant_id=slug,
                status_code=exc.status_code,
            )
            raise

    if "primary_color" in changes:
        if not _HEX_RX.match(changes["primary_color"]):
            emit_event(
                request,
                action="admin.branding.update",
                outcome="denied",
                reason="invalid_primary_color",
                tenant_id=slug,
                status_code=422,
            )
            raise HTTPException(422, "primary_color_must_be_hex_RRGGBB")

    try:
        with Session(get_engine()) as db:
            tenant = db.exec(select(Tenant).where(Tenant.slug == slug)).first()
            if tenant is None:
                tenant = Tenant(
                    slug=slug,
                    name=slug,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(tenant)
                db.flush()
            if "logo_url" in changes:
                tenant.logo_url = changes["logo_url"]
            if "primary_color" in changes:
                tenant.primary_color = changes["primary_color"]
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("branding update failed slug=%s err=%s", slug, err)
        emit_event(
            request,
            action="admin.branding.update",
            outcome="error",
            reason="db_error",
            tenant_id=slug,
            status_code=500,
        )
        raise HTTPException(500, "branding_update_failed") from err

    emit_event(
        request,
        action="admin.branding.update",
        outcome="success",
        tenant_id=tenant.slug,
        count=len(changes),
    )
    return _tenant_to_dict(tenant)
