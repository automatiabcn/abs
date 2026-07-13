# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Vault audit chain with HMAC tamper detection.

Each `VaultAuditEntry`:
  hmac = HMAC-SHA256(secret, canonical(entry) + prev_hmac)

`verify_chain()` walks rows in id order and recomputes; the first row whose
recomputed hmac doesn't match the stored hmac is the tamper point.

HMAC secret comes from `settings.vault_audit_hmac_secret`. Rotating that
secret invalidates the chain — a controlled re-init is required (`reseal_chain`).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, select

from app.config import settings
from app.db.models import VaultAuditEntry
from app.db.session import get_engine

logger = logging.getLogger(__name__)


def _canonical(entry: VaultAuditEntry) -> bytes:
    """Stable byte representation that does NOT include the hmac fields."""
    ts = entry.ts.isoformat() if isinstance(entry.ts, datetime) else str(entry.ts)
    parts = [
        str(entry.id or ""),
        ts,
        entry.action,
        entry.actor,
        entry.target_key or "",
        entry.detail or "",
    ]
    return "|".join(parts).encode("utf-8")


def _compute_hmac(entry: VaultAuditEntry, prev_hmac: str) -> str:
    secret = settings.vault_audit_hmac_secret.encode("utf-8")
    payload = _canonical(entry) + b"||" + prev_hmac.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def append_entry(
    *,
    action: str,
    actor: str = "system",
    target_key: Optional[str] = None,
    detail: Optional[str] = None,
) -> VaultAuditEntry:
    """Append a new audit entry; computes hmac chained from previous entry."""
    with Session(get_engine()) as db:
        last = db.scalars(
            select(VaultAuditEntry)
            .order_by(VaultAuditEntry.id.desc())  # type: ignore[union-attr]
            .limit(1)
        ).first()
        prev_hmac = last.hmac if last else ""
        entry = VaultAuditEntry(
            ts=datetime.now(timezone.utc),
            action=action,
            actor=actor,
            target_key=target_key,
            detail=detail,
            hmac="",
            prev_hmac=prev_hmac,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        # Now that we have the row id, compute final hmac.
        entry.hmac = _compute_hmac(entry, prev_hmac)
        db.add(entry)
        db.commit()
        db.refresh(entry)
    return entry


def verify_chain() -> dict:
    """Re-compute every entry's hmac; return integrity report.

    {
      "ok": bool,
      "total_entries": int,
      "tampered_entry_id": int | None,
      "elapsed_ms": float,
    }
    """
    started = time.perf_counter()
    tampered: Optional[int] = None
    total = 0
    with Session(get_engine()) as db:
        rows: List[VaultAuditEntry] = list(
            db.scalars(
                select(VaultAuditEntry).order_by(VaultAuditEntry.id)  # type: ignore[union-attr]
            ).all()
        )
        prev_hmac = ""
        for r in rows:
            total += 1
            if r.prev_hmac != prev_hmac:
                tampered = r.id
                break
            expected = _compute_hmac(r, prev_hmac)
            if expected != r.hmac:
                tampered = r.id
                break
            prev_hmac = r.hmac
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "ok": tampered is None,
        "total_entries": total,
        "tampered_entry_id": tampered,
        "elapsed_ms": elapsed_ms,
    }


def reseal_chain() -> dict:
    """Re-compute and re-store every hmac (use after rotating
    `vault_audit_hmac_secret`). Returns {resealed: int}."""
    with Session(get_engine()) as db:
        rows: List[VaultAuditEntry] = list(
            db.scalars(
                select(VaultAuditEntry).order_by(VaultAuditEntry.id)  # type: ignore[union-attr]
            ).all()
        )
        prev_hmac = ""
        for r in rows:
            r.prev_hmac = prev_hmac
            r.hmac = _compute_hmac(r, prev_hmac)
            db.add(r)
            prev_hmac = r.hmac
        db.commit()
    return {"resealed": len(rows)}


def stats(window_hours: int = 24, recent_limit: int = 50) -> dict:
    """Aggregate stats for `vault_audit_status` MCP tool."""
    now = datetime.now(timezone.utc)
    window_start = now.timestamp() - window_hours * 3600
    by_action: dict[str, int] = {}
    recent: list[dict] = []
    total = 0
    entries_24h = 0
    with Session(get_engine()) as db:
        rows = list(
            db.scalars(
                select(VaultAuditEntry).order_by(VaultAuditEntry.id.desc())  # type: ignore[union-attr]
            ).all()
        )
        total = len(rows)
        for r in rows:
            ts = r.ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts.timestamp() >= window_start:
                entries_24h += 1
            by_action[r.action] = by_action.get(r.action, 0) + 1
            if len(recent) < recent_limit:
                recent.append(
                    {
                        "id": r.id,
                        "ts": ts.isoformat(),
                        "action": r.action,
                        "actor": r.actor,
                        "target_key": r.target_key,
                    }
                )
    integrity = verify_chain()
    return {
        "audit_chain_integrity": "ok" if integrity["ok"] else "tampered",
        "tampered_entry_id": integrity["tampered_entry_id"],
        "verify_elapsed_ms": integrity["elapsed_ms"],
        "total_entries": total,
        "entries_24h": entries_24h,
        "by_action": by_action,
        "recent": recent,
    }
