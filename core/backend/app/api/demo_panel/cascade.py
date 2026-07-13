# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Provider cascade visualiser.

GET /v1/panel/cascade/recent?limit=100

Returns a list of synthesised cascade flows (best-effort, since we don't
yet persist a per-request trace table). For demo mode we read from the
in-process cascade tracker if available; otherwise we synthesise from
recent CustomerAuditEntry rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.auth import current_admin

# Signed-in operators only. Open, this told a stranger which providers a company
# uses and when its people are working — every tool call is a timestamp.
router = APIRouter(
    prefix="/v1/panel/cascade", tags=["panel"], dependencies=[Depends(current_admin)]
)


def _norm(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _synthesise_from_audit(limit: int) -> list[dict]:
    from sqlmodel import Session, select

    from app.db.models import CustomerAuditEntry
    from app.db.session import get_engine

    capped = max(1, min(int(limit), 500))
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    out: list[dict] = []
    with Session(get_engine()) as db:
        # DB-side filter + order + limit. The audit table grows with every tool
        # call; loading it all into memory per request was an unbounded memory/CPU
        # DoS. Fetch at most `capped` most-recent tool_call rows; the 7-day cutoff
        # is a cheap Python filter over that bounded set. (This route now requires
        # a signed-in operator, which it did not when that DoS was found — keep the
        # bound anyway: a signed-in caller can still ask for a lot.)
        rows = list(db.scalars(
            select(CustomerAuditEntry)
            .where(CustomerAuditEntry.action == "tool_call")
            .order_by(CustomerAuditEntry.ts.desc())
            .limit(capped)
        ).all())
    for r in rows:
        ts = _norm(r.ts)
        if ts is None or ts < cutoff:
            continue
        out.append(
            {
                "ts": ts.isoformat(),
                # license_jti intentionally NOT exposed on this unauthenticated
                # /v1/panel/* dashboard — it is a per-customer token identifier.
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


def _timeseries_24h(flows: list[dict]) -> list[dict]:
    """Hourly cascade-call buckets for the last 24h → [{ts, count}, …].

    Empty when there is no activity (panel shows a clean "Veri yok" instead
    of a flat-zero chart). Shape matches the frontend `CascadePoint`.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    buckets: dict[str, int] = {}
    for f in flows:
        raw = f.get("ts")
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(raw)
        except ValueError:
            continue
        ts = _norm(ts)
        if ts is None or ts < cutoff:
            continue
        hour = ts.replace(minute=0, second=0, microsecond=0)
        key = hour.isoformat()
        buckets[key] = buckets.get(key, 0) + 1
    return [{"ts": k, "count": buckets[k]} for k in sorted(buckets)]


def _active_provider_count() -> int:
    """Currently configured cascade providers (free-first default chain)."""
    try:
        from app.providers.cascade import get_active_providers

        return len(get_active_providers())
    except Exception:
        return 0


@router.get("/recent")
async def recent_cascade(limit: int = 100) -> dict:
    flows = _synthesise_from_audit(limit)
    return {
        "count": len(flows),
        "flows": flows,
        "providers_active": _active_provider_count(),
        "timeseries": _timeseries_24h(flows),
        "providers_seen": sorted(
            {p for f in flows for p in (f.get("cascade_path") or [])}
        ),
    }
