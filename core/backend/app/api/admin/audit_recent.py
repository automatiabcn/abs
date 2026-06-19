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


# Stable cross-source ordering: at an identical timestamp, vault rows sort
# before customer before webhook (matches the append order of the merge below).
# The cursor carries this source so the next page can resume *within* a tied
# timestamp instead of skipping every row that shares the boundary ts.
_SOURCE_RANK = {"vault": 0, "customer": 1, "webhook": 2}


def _encode_cursor(ts: datetime, source: str, row_id: str | int) -> str:
    raw = f"{ts.isoformat()}|{source}|{row_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(token: Optional[str]) -> Optional[tuple[datetime, Optional[str], Optional[str]]]:
    """Return (ts, source, row_id) or None. Back-compatible with the old
    ``ts|id`` (2-field) cursors, which decode to source=None and fall back to
    the plain ts boundary for that one in-flight page."""
    if not token:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        parts = raw.split("|", 2)
        if len(parts) == 3:
            ts_iso, source, row_id = parts
        elif len(parts) == 2:  # legacy ts|id cursor
            ts_iso, source, row_id = parts[0], None, parts[1]
        else:
            raise ValueError("cursor must have at least ts|id")
        dt = datetime.fromisoformat(ts_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt, source, row_id)
    except Exception as exc:
        raise HTTPException(400, f"invalid_cursor:{type(exc).__name__}") from exc


def _keyset(ts_col, id_col, source: str, anchor):
    """Build the WHERE clause that returns rows strictly *after* the cursor
    anchor in the (ts DESC, source-rank ASC, id DESC) total order, for one
    source. None when there is no cursor.

    Fixes the silent row-skip: the old code filtered every source by
    ``ts < cursor_ts``, so any rows sharing the boundary timestamp that hadn't
    been shown yet were dropped from pagination forever."""
    from sqlalchemy import and_, or_

    if anchor is None:
        return None
    ts_a, source_a, id_a = anchor
    if source_a is None:  # legacy cursor — no source/id tiebreaker available
        return ts_col < ts_a
    rank = _SOURCE_RANK.get(source, 99)
    rank_a = _SOURCE_RANK.get(source_a, 99)
    if rank < rank_a:
        # this source sorts before the anchor at ts_a → its ts_a rows were shown
        return ts_col < ts_a
    if rank > rank_a:
        # this source sorts after the anchor at ts_a → none of its ts_a rows shown
        return ts_col <= ts_a
    # same source as the anchor → resume within the tied ts using the id.
    # webhook's PK (event_id) is a string; vault/customer ids are ints.
    id_typed: object = id_a
    if source != "webhook":
        try:
            id_typed = int(id_a)
        except (TypeError, ValueError):
            id_typed = id_a
    return or_(ts_col < ts_a, and_(ts_col == ts_a, id_col < id_typed))


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
    anchor = _decode_cursor(cursor)

    out: list[dict] = []
    with Session(get_engine()) as db:
        if source in {"vault", "all"}:
            stmt = select(VaultAuditEntry)
            kc = _keyset(VaultAuditEntry.ts, VaultAuditEntry.id, "vault", anchor)
            if kc is not None:
                stmt = stmt.where(kc)
            stmt = stmt.order_by(
                VaultAuditEntry.ts.desc(), VaultAuditEntry.id.desc()
            ).limit(effective_limit)
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
            kc = _keyset(
                CustomerAuditEntry.ts, CustomerAuditEntry.id, "customer", anchor
            )
            if kc is not None:
                stmt = stmt.where(kc)
            stmt = stmt.order_by(
                CustomerAuditEntry.ts.desc(), CustomerAuditEntry.id.desc()
            ).limit(effective_limit)
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
            kc = _keyset(
                WebhookEvent.received_at, WebhookEvent.event_id, "webhook", anchor
            )
            if kc is not None:
                stmt = stmt.where(kc)
            stmt = stmt.order_by(
                WebhookEvent.received_at.desc(), WebhookEvent.event_id.desc()
            ).limit(effective_limit)
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
                datetime.fromisoformat(last["ts"]), last["source"], last["id"]
            )
    return {
        "source": source,
        "count": len(page),
        "limit": effective_limit,
        "cursor": next_cursor,
        "entries": page,
    }
