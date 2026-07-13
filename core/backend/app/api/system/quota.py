# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""CJ-009 / Sprint 20 — `/v1/system/quota_status` endpoint.

`/api/quota-status` (legacy stub) ile karistirma — bu endpoint Claude Plus
+ ucretsiz saglayicilarin gercek kullanim/limit verisini birlestirir ve
80%/95% threshold uyarilarini birlikte yayar.
"""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth import current_admin

from app.providers.cascade import configured_map
from app.services.quota_monitor import (
    QUOTAS,
    current_period,
    get_monthly_usage,
    threshold_warnings,
)

# How much of each provider's allowance a company has burned, and which
# providers it has configured at all. That is operator data, and it was readable
# by anyone who could reach the server — while `/v1/quota/status`, the near-twin
# route next door, was correctly behind a login the whole time.
router = APIRouter(
    prefix="/v1/system", tags=["system"], dependencies=[Depends(current_admin)]
)


class QuotaSlice(BaseModel):
    used: int
    limit: int
    percent: float = Field(..., ge=0.0)
    label: str
    configured: bool = True


class QuotaStatus(BaseModel):
    claude_plus: QuotaSlice
    free_providers: Dict[str, QuotaSlice]
    warnings: List[str]
    period_start: str
    period_end: str


def _slice(provider: str, used: int, limit: int, configured: bool) -> QuotaSlice:
    pct = (used / limit) if limit else 0.0
    return QuotaSlice(
        used=used,
        limit=limit,
        percent=round(pct, 4),
        label=QUOTAS.get(provider, {}).get("label", provider),
        configured=configured,
    )


@router.get("/quota_status", response_model=QuotaStatus)
async def quota_status() -> QuotaStatus:
    start, now = current_period()
    configured = configured_map()

    cp_used, cp_limit = await get_monthly_usage("anthropic", start, now)
    claude_slice = _slice(
        "anthropic", cp_used, cp_limit, configured.get("anthropic", False)
    )

    free_providers: Dict[str, QuotaSlice] = {}
    warnings: List[str] = list(threshold_warnings(claude_slice.percent, "claude_plus"))

    for provider in ("groq", "gemini", "cerebras", "cohere", "cloudflare"):
        used, limit = await get_monthly_usage(provider, start, now)
        sl = _slice(provider, used, limit, configured.get(provider, False))
        free_providers[provider] = sl
        warnings.extend(threshold_warnings(sl.percent, provider))

    return QuotaStatus(
        claude_plus=claude_slice,
        free_providers=free_providers,
        warnings=warnings,
        period_start=start.isoformat(),
        period_end=now.isoformat(),
    )
