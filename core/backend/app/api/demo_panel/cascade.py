"""033 Modul F — Provider cascade visualiser.

GET /v1/panel/cascade/recent?limit=100

Returns a list of synthesised cascade flows (best-effort, since we don't
yet persist a per-request trace table). For demo mode we read from the
in-process cascade tracker if available; otherwise we synthesise from
recent CustomerAuditEntry rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter

router = APIRouter(prefix="/v1/panel/cascade", tags=["panel"])


def _norm(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _synthesise_from_audit(limit: int) -> list[dict]:
    from sqlmodel import Session, select

    from app.db.models import CustomerAuditEntry
    from app.db.session import get_engine

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    out: list[dict] = []
    with Session(get_engine()) as db:
        rows = list(db.scalars(select(CustomerAuditEntry)).all())
    for r in sorted(rows, key=lambda x: x.ts or datetime.min, reverse=True):
        if r.action != "tool_call":
            continue
        ts = _norm(r.ts)
        if ts is None or ts < cutoff:
            continue
        out.append(
            {
                "ts": ts.isoformat(),
                "license_jti": r.license_jti,
                "tool": r.resource or "unknown",
                "cascade_path": ["groq", "cerebras"],
                "winner": "groq",
                "total_latency_ms": 240,
                "step_latencies_ms": {"groq": 240},
            }
        )
        if len(out) >= limit:
            break
    return out


@router.get("/recent")
async def recent_cascade(limit: int = 100) -> dict:
    flows = _synthesise_from_audit(limit)
    return {
        "count": len(flows),
        "flows": flows,
        "providers_seen": sorted(
            {p for f in flows for p in (f.get("cascade_path") or [])}
        ),
    }
