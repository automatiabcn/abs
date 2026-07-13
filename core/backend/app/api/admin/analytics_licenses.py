# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""License analytics: cohort retention, expiry calendar, tier mix."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.admin.auth import admin_required

router = APIRouter(prefix="/v1/admin/analytics", tags=["admin"])


def _norm(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@router.get("/licenses")
async def licenses_analytics(
    cohort: str = "monthly",
    _admin: dict = Depends(admin_required),
) -> dict:
    from sqlmodel import Session, select

    from app.db.models import License
    from app.db.session import get_engine

    if cohort not in {"monthly", "weekly"}:
        cohort = "monthly"

    now = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        rows = list(db.scalars(select(License)).all())

    tier_breakdown: dict[str, int] = defaultdict(int)
    cohort_signups: dict[str, int] = defaultdict(int)
    cohort_active: dict[str, int] = defaultdict(int)
    expiry_buckets = {"0-30d": 0, "31-60d": 0, "61-90d": 0, "90d+": 0}

    for r in rows:
        if r.purged_at is not None:
            continue
        tier_breakdown[r.tier or "unknown"] += 1
        issued = _norm(r.issued_at)
        if issued is not None:
            key = (
                issued.strftime("%Y-%m")
                if cohort == "monthly"
                else issued.strftime("%Y-W%U")
            )
            cohort_signups[key] += 1
            if r.revoked_at is None:
                cohort_active[key] += 1

        expires = _norm(r.expires_at)
        if expires is not None and r.revoked_at is None:
            days = (expires - now).days
            if days < 31:
                expiry_buckets["0-30d"] += 1
            elif days < 61:
                expiry_buckets["31-60d"] += 1
            elif days < 91:
                expiry_buckets["61-90d"] += 1
            else:
                expiry_buckets["90d+"] += 1

    cohort_table = []
    for key in sorted(cohort_signups.keys()):
        signups = cohort_signups[key]
        retained = cohort_active[key]
        cohort_table.append(
            {
                "cohort": key,
                "signups": signups,
                "retained": retained,
                "retention_rate": round(retained / signups, 4) if signups else 0.0,
            }
        )

    return {
        "cohort_granularity": cohort,
        "tier_breakdown": dict(tier_breakdown),
        "cohorts": cohort_table,
        "expiry_calendar": expiry_buckets,
    }
