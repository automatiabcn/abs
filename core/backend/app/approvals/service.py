# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Approval Center service — persist agent runs + approval items, decide them.

All operations are tenant-scoped (``WHERE tenant_slug``); on Postgres the RLS
policy (0020) is the DB-tier safety net. Decisions are best-effort audited.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import update as sa_update
from sqlmodel import Session, select

from app.db.models import AgentRun, ApprovalItem
from app.db.session import get_engine

logger = logging.getLogger(__name__)

_DECISIONS = {"approve": "approved", "reject": "rejected", "edit": "edited"}


def _claim_pending_transition(
    db: Session, *, item_id: int, tenant_slug: str, new_status: str
) -> bool:
    """Atomically move an approval item out of ``pending``.

    Returns True only for the caller whose UPDATE actually performed the
    transition (rowcount 1). Concurrent decides (double-click / two browser
    tabs) both read ``status == "pending"`` before either commits, so a plain
    read-then-write gate fires the action twice; this conditional UPDATE lets
    exactly one caller win. Mirrors the OAuth refresh atomic-rotation claim."""
    claim = (
        sa_update(ApprovalItem)
        .where(ApprovalItem.id == item_id)
        .where(ApprovalItem.tenant_slug == tenant_slug)
        .where(ApprovalItem.status == "pending")
        .values(status=new_status)
    )
    return (db.execute(claim).rowcount or 0) == 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def log_agent_run(
    result: Any, *, tenant_slug: str, actor: str = "", task: str = ""
) -> int:
    """Persist one agent execution; returns the AgentRun id."""
    row = AgentRun(
        tenant_slug=tenant_slug or "default",
        agent_id=result.agent_id,
        task=(task or getattr(result, "task", "") or "")[:8000],
        summary=(result.summary or "")[:4096],
        confidence=float(result.confidence or 0.0),
        risk=result.risk,
        requires_approval=bool(result.requires_approval),
        provider=result.provider or "",
        evidence_json=json.dumps([e.to_dict() for e in result.evidence])[:65000],
        payload_json=json.dumps(result.payload or {})[:65000],
        elapsed_ms=int(result.elapsed_ms or 0),
        actor=actor or "",
    )
    with Session(get_engine()) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)


def create_approval_from_result(
    result: Any,
    *,
    tenant_slug: str,
    requester: str,
    agent_run_id: Optional[int] = None,
    target_company: str = "",
    target_person: str = "",
    channel: str = "",
    consent_status: str = "",
) -> dict:
    """Turn an approval-gated agent result into a pending ApprovalItem."""
    proposed = ""
    if isinstance(result.payload, dict):
        proposed = str(
            result.payload.get("message") or result.payload.get("draft") or ""
        )
    row = ApprovalItem(
        tenant_slug=tenant_slug or "default",
        agent_id=result.agent_id,
        agent_run_id=agent_run_id,
        action=(result.recommended_action or result.summary or "")[:1024],
        target_company=target_company[:256],
        target_person=target_person[:256],
        channel=channel[:64],
        rationale=(result.summary or "")[:4096],
        evidence_json=json.dumps([e.to_dict() for e in result.evidence])[:65000],
        proposed_message=(proposed or result.recommended_action or "")[:8192],
        risk=result.risk,
        consent_status=consent_status[:32],
        policy_result="requires_approval",
        status="pending",
        escalate_at=_now() + timedelta(hours=4),
    )
    with Session(get_engine()) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        return _to_dict(row)


def _is_escalation_due(r: ApprovalItem) -> bool:
    """A pending item is overdue for escalation once its `escalate_at` (set to
    +4h at creation) has passed. tz-naive timestamps (SQLite) are treated as
    UTC. Decided items never escalate."""
    esc = r.escalate_at
    if esc is None or r.status != "pending":
        return False
    if esc.tzinfo is None:
        esc = esc.replace(tzinfo=timezone.utc)
    return esc <= _now()


def _to_dict(r: ApprovalItem) -> dict:
    return {
        "id": r.id,
        "agent_id": r.agent_id,
        "agent_run_id": r.agent_run_id,
        "action": r.action,
        "target_company": r.target_company,
        "target_person": r.target_person,
        "channel": r.channel,
        "rationale": r.rationale,
        "evidence": json.loads(r.evidence_json or "[]"),
        "proposed_message": r.proposed_message,
        "risk": r.risk,
        "consent_status": r.consent_status,
        "policy_result": r.policy_result,
        "status": r.status,
        "decided_by": r.decided_by,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        "outcome": r.outcome,
        # escalate_at was set at creation but never surfaced or read — a dead
        # field. Expose it + a computed `escalation_due` so the panel can flag
        # pending items past their 4h SLA. (Notification/cron is a follow-up.)
        "escalate_at": r.escalate_at.isoformat() if r.escalate_at else None,
        "escalation_due": _is_escalation_due(r),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def list_approvals(
    *, tenant_slug: str, status: str = "pending", limit: int = 100
) -> Dict[str, Any]:
    """Items for a tenant + risk-bucket summary for the Approval Center header."""
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        q = select(ApprovalItem).where(ApprovalItem.tenant_slug == tenant_slug)
        if status and status != "all":
            q = q.where(ApprovalItem.status == status)
        rows = list(db.exec(q.order_by(ApprovalItem.created_at.desc()).limit(limit)))
        pending = list(
            db.exec(
                select(ApprovalItem).where(
                    ApprovalItem.tenant_slug == tenant_slug,
                    ApprovalItem.status == "pending",
                )
            )
        )
    buckets = {"low": 0, "medium": 0, "high": 0}
    for p in pending:
        buckets[p.risk] = buckets.get(p.risk, 0) + 1

    # Tier scorecards (mockup 04): low-risk auto-executed runs, and the
    # human-approval accept rate from decided items.
    from app.db.models import AgentRun

    with Session(get_engine()) as db:
        low_auto = len(
            db.exec(
                select(AgentRun).where(
                    AgentRun.tenant_slug == tenant_slug, AgentRun.risk == "low"
                )
            ).all()
        )
        decided = db.exec(
            select(ApprovalItem).where(
                ApprovalItem.tenant_slug == tenant_slug,
                ApprovalItem.status.in_(["approved", "edited", "rejected"]),  # type: ignore[attr-defined]
            )
        ).all()
    approved = sum(1 for x in decided if x.status in ("approved", "edited"))
    # 3rd-eye audit — with no decided items there is no accept rate; emit None so
    # the panel shows "—". The old `else 91` fabricated a 91% rate that rendered
    # as a real scorecard number on every fresh/empty install.
    accept_rate = round(approved / len(decided) * 100) if decided else None

    escalations_due = sum(1 for p in pending if _is_escalation_due(p))

    return {
        "items": [_to_dict(r) for r in rows],
        "pending_total": len(pending),
        "escalations_due": escalations_due,
        "by_risk": buckets,
        "tier_stats": {
            "low_auto": low_auto,
            "medium_pending": buckets["medium"],
            "high_pending": buckets["high"],
            "accept_rate": accept_rate,
        },
    }


def recent_agent_runs(*, tenant_slug: str, limit: int = 20) -> List[dict]:
    """Latest agent executions for the dashboard activity feed (tenant-scoped)."""
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        rows = list(
            db.exec(
                select(AgentRun)
                .where(AgentRun.tenant_slug == tenant_slug)
                .order_by(AgentRun.created_at.desc())
                .limit(limit)
            )
        )
    return [
        {
            "id": r.id,
            "agent_id": r.agent_id,
            "summary": r.summary,
            "confidence": r.confidence,
            "risk": r.risk,
            "requires_approval": r.requires_approval,
            "provider": r.provider,
            "elapsed_ms": r.elapsed_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def get_approval(*, tenant_slug: str, item_id: int) -> Optional[dict]:
    with Session(get_engine()) as db:
        row = db.get(ApprovalItem, item_id)
        if row is None or row.tenant_slug != (tenant_slug or "default").strip():
            return None
        return _to_dict(row)


class AlreadyDecided(Exception):
    """Someone tried to decide an item that has already been decided.

    The action was never at risk — `won_transition` sees to that, and a second
    decision has never re-fired anything. What was at risk was the record. A
    re-decide used to overwrite `status` and return 200, so an item a person
    had *rejected* could be left reading "approved", with a decided_at to match
    and nothing sent. The operator reads that row later and believes a message
    went out that never did. A decision is a fact about what a person chose;
    it does not get rewritten.
    """


def decide_approval(
    *,
    tenant_slug: str,
    item_id: int,
    decision: str,
    decided_by: str,
    note: str = "",
    edited_message: str = "",
) -> Optional[dict]:
    """Approve / reject / edit a pending item. Tenant-scoped; returns the row."""
    status = _DECISIONS.get((decision or "").strip())
    if status is None:
        raise ValueError(f"invalid decision: {decision}")
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        row = db.get(ApprovalItem, item_id)
        if row is None or row.tenant_slug != tenant_slug:
            return None
        prev_status = row.status  # to fire the action at most once
        if prev_status != "pending":
            # Refused, not silently rewritten. The concurrent case is different
            # and stays as it was: two decides that race both see "pending", one
            # wins the claim below, and the loser is told the truth — the item is
            # decided — rather than being turned into a second send.
            raise AlreadyDecided(
                f"this was already {prev_status}; a decision cannot be taken back"
            )
        # Claim the pending→decided transition atomically so the action fires
        # at most once even under concurrent decides (a read-then-write check on
        # prev_status races). Only the winner gets won_transition=True.
        won_transition = False
        if prev_status == "pending":
            won_transition = _claim_pending_transition(
                db, item_id=item_id, tenant_slug=tenant_slug, new_status=status
            )
            db.expire(row, ["status"])
        row.status = status
        row.decided_by = decided_by or ""
        row.decided_at = _now()
        if edited_message:
            row.proposed_message = edited_message[:8192]
        if note:
            row.outcome = note[:512]
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(
            "approval_decision id=%s status=%s by=%s tenant=%s prev=%s",
            item_id,
            status,
            decided_by,
            tenant_slug,
            prev_status,
        )

    # Stage E — the FIRST approve/edit fires the action (consent-gated outbox);
    # re-deciding an already-decided item — or losing the concurrent claim —
    # never re-fires it (idempotent).
    action = None
    if status in ("approved", "edited") and won_transition:
        try:
            from app.actions import execute_for_approval

            action = execute_for_approval(row, tenant_slug=tenant_slug)
            if not note:  # surface the action outcome on the item
                with Session(get_engine()) as db2:
                    r2 = db2.get(ApprovalItem, item_id)
                    if r2 is not None:
                        r2.outcome = f"{action['status']}: {action['reason']}"[:512]
                        db2.add(r2)
                        db2.commit()
                        db2.refresh(r2)
                        row = r2
        except Exception:  # noqa: BLE001 — action best-effort; decision already saved
            logger.info("approval action execution skipped", exc_info=True)

    out = _to_dict(row)
    out["action"] = action
    return out
