"""033 Modul A — Demo mode status endpoint."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/v1/demo-mode", tags=["demo"])

_BOOT_TS = time.time()


@router.get("/status")
async def demo_mode_status() -> dict:
    return {
        "enabled": bool(settings.demo_mode),
        "mock_providers": bool(settings.provider_mock),
        "seed_version": settings.demo_seed_version,
        "started_at": datetime.fromtimestamp(_BOOT_TS, tz=timezone.utc).isoformat(),
    }
