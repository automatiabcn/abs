"""Provider quota radar endpoint'i (stub).

Gerçek cascade kotası 006-provider-cascade task'ında bağlanacak.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.auth import current_admin

router = APIRouter(prefix="/api", tags=["quota"])


@router.get("/quota-status")
async def get_quota_status(_admin: dict = Depends(current_admin)) -> dict:
    return {
        "status": "empty",
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        "providers": {
            "anthropic": {"used": 0, "limit": None, "pct": 0},
            "groq": {"used": 0, "limit": None, "pct": 0},
            "cerebras": {"used": 0, "limit": None, "pct": 0},
            "gemini": {"used": 0, "limit": None, "pct": 0},
            "cloudflare": {"used": 0, "limit": None, "pct": 0},
            "cohere": {"used": 0, "limit": 1000, "pct": 0},
        },
        "note": "Gerçek cascade quota verisi 006-provider-cascade task'ında bağlanacak",
    }
