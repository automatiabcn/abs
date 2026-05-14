# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""032 Modul G — Unified audit log viewer.

GET /v1/admin/audit/recent?limit=200&source=vault|customer|webhook|all&cursor=<b64>
Combines VaultAuditEntry (027), CustomerAuditEntry (029) and WebhookEvent (017).

Sprint 2I UAT-034 — pagination is now mandatory. The previous
`db.scalars(select(...)).all()` walk loaded every row into Python before
sorting; a tenant with 1M+ rows would OOM the worker. Each source is now
ordered + limited at the SQL layer (max 1000), and the optional ``cursor``
param resumes from the previous page's last timestamp.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.admin.auth import admin_required

router = APIRouter(prefix="/v1/admin/audit", tags=["admin"])


DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


def _norm(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _encode_cursor(ts: datetime, row_id: str | int) -> str:
    raw = f"{ts.isoformat()}|{row_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(token: Optional[str]) -> Optional[datetime]:
    if not token:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        ts_iso, _id = raw.split("|", 1)
        dt = datetime.fromisoformat(ts_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as exc:
        raise HTTPException(400, f"invalid_cursor:{type(exc).__name__}") from exc


@router.get("/recent")
async def recent_audit(
    limit: int = DEFAULT_LIMIT,
    source: str = "all",
    cursor: Optional[str] = None,
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
    # Honour the explicit `limit=0` contract (returns empty) while still
    # capping abusive callers at MAX_LIMIT.
    if limit <= 0:
        return {
            "source": source,
            "count": 0,
            "limit": 0,
            "cursor": None,
            "entries": [],
        }
    effective_limit = min(limit, MAX_LIMIT)
    cursor_ts = _decode_cursor(cursor)

    out: list[dict] = []
    with Session(get_engine()) as db:
        if source in {"vault", "all"}:
            stmt = select(VaultAuditEntry)
            if cursor_ts is not None:
                stmt = stmt.where(VaultAuditEntry.ts < cursor_ts)
            stmt = stmt.order_by(VaultAuditEntry.ts.desc()).limit(effective_limit)
            for r in db.scalars(stmt).all():
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
            stmt = select(CustomerAuditEntry)
            if cursor_ts is not None:
                stmt = stmt.where(CustomerAuditEntry.ts < cursor_ts)
            stmt = stmt.order_by(CustomerAuditEntry.ts.desc()).limit(effective_limit)
            for r in db.scalars(stmt).all():
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
            stmt = select(WebhookEvent)
            if cursor_ts is not None:
                stmt = stmt.where(WebhookEvent.received_at < cursor_ts)
            stmt = stmt.order_by(WebhookEvent.received_at.desc()).limit(effective_limit)
            for r in db.scalars(stmt).all():
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
    page = out[:effective_limit]
    next_cursor: Optional[str] = None
    # If this page filled the request, hand back a cursor so the caller
    # can ask for the next slice. (False positives — last page exactly
    # filled — cost only an empty follow-up call.)
    if page and len(page) == effective_limit:
        last = page[-1]
        if last["ts"]:
            next_cursor = _encode_cursor(
                datetime.fromisoformat(last["ts"]), last["id"]
            )
    return {
        "source": source,
        "count": len(page),
        "limit": effective_limit,
        "cursor": next_cursor,
        "entries": page,
    }
