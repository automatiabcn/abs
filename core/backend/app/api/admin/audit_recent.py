# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""032 Modul G — Unified audit log viewer.

GET /v1/admin/audit/recent?limit=200&source=vault|customer|webhook|all
Combines VaultAuditEntry (027), CustomerAuditEntry (029) and WebhookEvent (017).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.admin.auth import admin_required

router = APIRouter(prefix="/v1/admin/audit", tags=["admin"])


def _norm(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@router.get("/recent")
async def recent_audit(
    limit: int = 200,
    source: str = "all",
    _admin: dict = Depends(admin_required),
) -> dict:
    from sqlmodel import Session, select

    from app.db.models import (
        CustomerAuditEntry,
        VaultAuditEntry,
        WebhookEvent,
    )
    from app.db.session import get_engine

    if source not in {"vault", "customer", "webhook", "all"}:
        source = "all"
    out: list[dict] = []
    with Session(get_engine()) as db:
        if source in {"vault", "all"}:
            for r in db.scalars(select(VaultAuditEntry)).all():
                ts = _norm(r.ts)
                out.append(
                    {
                        "source": "vault",
                        "id": r.id,
                        "ts": ts.isoformat() if ts else None,
                        "action": r.action,
                        "actor": r.actor,
                        "target": r.target_key,
                        "detail": r.detail,
                    }
                )
        if source in {"customer", "all"}:
            for r in db.scalars(select(CustomerAuditEntry)).all():
                ts = _norm(r.ts)
                out.append(
                    {
                        "source": "customer",
                        "id": r.id,
                        "ts": ts.isoformat() if ts else None,
                        "action": r.action,
                        "license_jti": r.license_jti,
                        "detail": r.detail,
                    }
                )
        if source in {"webhook", "all"}:
            for r in db.scalars(select(WebhookEvent)).all():
                ts = _norm(r.received_at)
                out.append(
                    {
                        "source": "webhook",
                        "id": r.event_id,
                        "ts": ts.isoformat() if ts else None,
                        "action": r.event_type,
                        "license_jti": r.license_jti,
                        "error": r.error,
                    }
                )

    out.sort(key=lambda r: r["ts"] or "", reverse=True)
    return {"source": source, "count": len(out[:limit]), "entries": out[:limit]}
