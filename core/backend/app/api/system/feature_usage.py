"""S20.3 — /v1/system/feature_usage endpoint."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.api.auth import current_admin
from app.services import feature_usage as feature_usage_service

router = APIRouter(prefix="/v1/system", tags=["system"])


@router.get("/feature_usage")
async def feature_usage(_admin: dict = Depends(current_admin)) -> Dict[str, Any]:
    rows = feature_usage_service.get_usage(tenant_slug="default")
    return {
        "tenant_slug": "default",
        "feature_count": len(feature_usage_service.FEATURE_IDS),
        "features": rows,
    }
