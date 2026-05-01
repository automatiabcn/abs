"""032 Modul E — Churn detection.

Heuristic: per-license tool-call rate over last 7 days vs. last 30 days.
If `last_7d_avg < threshold * last_30d_avg` (default 0.5) the license is flagged.
Source: CustomerAuditEntry rows (action='tool_call' or any action).

Optional Discord alert when flag count exceeds 3.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.admin.auth import admin_required
from app.config import settings

router = APIRouter(prefix="/v1/admin/analytics", tags=["admin"])
logger = logging.getLogger(__name__)


def _norm(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _compute_churn_flags(threshold: Optional[float] = None) -> dict:
    from sqlmodel import Session, select

    from app.db.models import CustomerAuditEntry, License
    from app.db.session import get_engine

    if threshold is None:
        threshold = settings.churn_threshold

    now = datetime.now(timezone.utc)
    last_7 = now - timedelta(days=7)
    last_30 = now - timedelta(days=30)

    counts_7d: dict[str, int] = defaultdict(int)
    counts_30d: dict[str, int] = defaultdict(int)

    with Session(get_engine()) as db:
        rows = list(db.scalars(select(CustomerAuditEntry)).all())
        active = {
            lic.jti: lic
            for lic in db.scalars(select(License)).all()
            if lic.revoked_at is None and lic.purged_at is None
        }

    for r in rows:
        ts = _norm(r.ts)
        if ts is None or r.license_jti not in active:
            continue
        if ts >= last_30:
            counts_30d[r.license_jti] += 1
        if ts >= last_7:
            counts_7d[r.license_jti] += 1

    flagged = []
    for jti in active:
        avg_7d = counts_7d.get(jti, 0) / 7
        avg_30d = counts_30d.get(jti, 0) / 30
        if avg_30d == 0:
            continue
        ratio = avg_7d / avg_30d
        if ratio < threshold:
            flagged.append(
                {
                    "license_jti": jti,
                    "customer_email": active[jti].customer_email or "",
                    "avg_7d_actions_per_day": round(avg_7d, 3),
                    "avg_30d_actions_per_day": round(avg_30d, 3),
                    "ratio": round(ratio, 3),
                }
            )

    return {
        "threshold": threshold,
        "flagged_count": len(flagged),
        "flagged": flagged,
    }


@router.get("/churn")
async def churn(
    threshold: Optional[float] = None,
    _admin: dict = Depends(admin_required),
) -> dict:
    result = _compute_churn_flags(threshold)
    if result["flagged_count"] > 3:
        try:
            from app.integrations import discord_webhook as dw

            if hasattr(dw, "notify_milestone"):
                dw.notify_milestone(
                    metric="churn_flag_count_exceeded_3",
                    value=result["flagged_count"],
                )
        except Exception as exc:
            logger.info("churn discord alert failed: %s", exc)
    return result
