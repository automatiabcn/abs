"""032 Modul F — Recent error monitor.

GET /v1/admin/errors/recent?limit=100&severity=error|warn|all

Sources:
  - WebhookEvent rows where error IS NOT NULL
  - EmailQueue rows where error IS NOT NULL
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.admin.auth import admin_required

router = APIRouter(prefix="/v1/admin/errors", tags=["admin"])


def _norm(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@router.get("/recent")
async def recent_errors(
    limit: int = 100,
    severity: str = "all",
    _admin: dict = Depends(admin_required),
) -> dict:
    from sqlmodel import Session, select

    from app.db.models import EmailQueue, WebhookEvent
    from app.db.session import get_engine

    if severity not in {"error", "warn", "all"}:
        severity = "all"
    out: list[dict] = []
    with Session(get_engine()) as db:
        for r in db.scalars(select(WebhookEvent)).all():
            if not r.error:
                continue
            ts = _norm(r.received_at)
            out.append(
                {
                    "source": "webhook",
                    "id": r.event_id,
                    "ts": ts.isoformat() if ts else None,
                    "severity": "error",
                    "message": r.error[:512],
                }
            )
        for r in db.scalars(select(EmailQueue)).all():
            if not r.error:
                continue
            ts = _norm(r.scheduled_at)
            sev = "error" if (r.attempts or 0) >= 3 else "warn"
            out.append(
                {
                    "source": "email",
                    "id": r.id,
                    "ts": ts.isoformat() if ts else None,
                    "severity": sev,
                    "message": r.error[:512],
                }
            )

    if severity != "all":
        out = [r for r in out if r["severity"] == severity]
    out.sort(key=lambda r: r["ts"] or "", reverse=True)
    return {"count": len(out[:limit]), "errors": out[:limit]}
