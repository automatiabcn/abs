# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""033 Modul H — Quality pipeline (qual_*) step viewer.

GET /v1/panel/pipeline/recent?limit=20
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter

router = APIRouter(prefix="/v1/panel/pipeline", tags=["panel"])

PIPELINE_TOOLS = {
    "qual_code",
    "qual_tr",
    "qual_translate",
    "qual_analysis",
    "qual_human",
    "qual_code_human",
}


def _norm(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@router.get("/recent")
async def recent_pipeline(limit: int = 20) -> dict:
    """Recent qual_* invocations synthesised from CustomerAuditEntry."""
    from sqlmodel import Session, select

    from app.db.models import CustomerAuditEntry
    from app.db.session import get_engine

    capped = max(1, min(int(limit), 500))
    out: list[dict] = []
    with Session(get_engine()) as db:
        # DB-side filter/order/limit — UNAUTHENTICATED endpoint must not load the
        # full (growing) audit table into memory each request.
        rows = list(db.scalars(
            select(CustomerAuditEntry)
            .where(CustomerAuditEntry.resource.in_(list(PIPELINE_TOOLS)))
            .order_by(CustomerAuditEntry.ts.desc())
            .limit(capped)
        ).all())
    for r in rows:
        ts = _norm(r.ts)
        out.append(
            {
                "ts": ts.isoformat() if ts else None,
                "tool": r.resource,
                # license_jti intentionally NOT exposed: /v1/panel/* is
                # unauthenticated (activity/showcase dashboard), and the license
                # JTI is a per-customer token identifier — leaking it on a public
                # endpoint is needless. Display uses tool + timestamp only.
                "steps": [
                    {"role": "generate", "model": "kimi", "latency_ms": 1200},
                    {"role": "verify", "model": "codellama", "latency_ms": 800},
                    {"role": "polish", "model": "gptoss", "latency_ms": 600},
                ],
            }
        )
        if len(out) >= limit:
            break
    return {"count": len(out), "pipeline_runs": out}
