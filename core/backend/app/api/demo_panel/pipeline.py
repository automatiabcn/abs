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

    out: list[dict] = []
    with Session(get_engine()) as db:
        rows = list(db.scalars(select(CustomerAuditEntry)).all())
    for r in sorted(rows, key=lambda x: x.ts or datetime.min, reverse=True):
        if (r.resource or "") not in PIPELINE_TOOLS:
            continue
        ts = _norm(r.ts)
        out.append(
            {
                "ts": ts.isoformat() if ts else None,
                "tool": r.resource,
                "license_jti": r.license_jti,
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
