"""Q12-R84 — Admin dashboard widget pricing endpoint.

GET /v1/admin/widget_pricing → revenue multiplier + tier list prices.

Source of truth is settings (env). Default 0.0 → admin UI shows "$0/mo"
until operator configures real prices in their .env.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.admin.auth import admin_required
from app.config import settings

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/widget_pricing")
async def widget_pricing(_admin: dict = Depends(admin_required)) -> dict:
    return {
        "revenue_widget_multiplier": settings.abs_revenue_widget_multiplier,
        "seat_price_self_host": settings.abs_seat_price_self_host,
        "seat_price_team_5": settings.abs_seat_price_team_5,
        "seat_price_team_10": settings.abs_seat_price_team_10,
    }
