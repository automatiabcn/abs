# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""S20.3 — /v1/system/feature_usage endpoint."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.api.auth import current_admin
from app.api.chat import _resolve_tenant
from app.services import feature_usage as feature_usage_service

router = APIRouter(prefix="/v1/system", tags=["system"])


@router.get("/feature_usage")
async def feature_usage(admin: dict = Depends(current_admin)) -> Dict[str, Any]:
    # Was hardcoded to "default" — every admin saw the default tenant's
    # counters. Resolve the caller's own tenant (falls back to "default"
    # for single-tenant deploys).
    tenant = _resolve_tenant(str(admin.get("sub") or "")) or "default"
    rows = feature_usage_service.get_usage(tenant_slug=tenant)
    return {
        "tenant_slug": tenant,
        "feature_count": len(feature_usage_service.FEATURE_IDS),
        "features": rows,
    }
