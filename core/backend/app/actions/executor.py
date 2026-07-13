# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Action executor — fire an approved agent action, gated by consent (Stage E).

The approval → action bridge. When a reviewer approves an Approval Center item,
this runs its action and records the outcome in the ActionExecution outbox:

  • internal actions (CRM note, merge, field update, route) apply immediately;
  • outbound comms (email / whatsapp / sms / voice) are consent-gated via the
    Consent Ledger (fail-closed) and, when allowed, queued to the channel.

No silent sends: outbound never goes out without an opt-in consent record. Every
attempt — executed, queued, blocked or failed — is persisted, tenant-scoped.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from app.agentic.approvals_bridge import AGENT_TOOL_CHANNEL
from app.consent.service import check_channel
from app.db.growth_models import ActionExecution, Company, Contact
from app.db.session import get_engine

logger = logging.getLogger(__name__)

# outbound comms channels (consent-gated) → the Consent Ledger column key
_COMMS = {"email", "phone", "sms", "whatsapp", "voice", "call"}
_GATE_CHANNEL = {"voice": "phone", "call": "phone"}

# gate reason code → the outcome text an operator reads in the outbox
_REASON_TEXT = {
    "no_consent_on_file": "no consent record on file (fail-closed)",
    "channel_not_consented": "no consent for this channel",
    "opted_out": "opted out — not sent",
    "do_not_call": "do-not-call list",
    "consent_granted": "consent on file · queued to the channel",
}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _resolve_contact_email(db: Session, tenant: str, company_name: str) -> Optional[str]:
    """Primary contact email for the approval's target company (consent key)."""
    if not company_name:
        return None
    companies = db.exec(select(Company).where(Company.tenant_slug == tenant)).all()
    company = next((c for c in companies if _norm(c.name) == _norm(company_name)), None)
    if company is None:
        return None
    contact = db.exec(
        select(Contact).where(
            Contact.tenant_slug == tenant,
            Contact.company_id == company.id,
            Contact.email.is_not(None),  # type: ignore[union-attr]
        )
    ).first()
    return contact.email if contact else None


def _record(db: Session, **kw: Any) -> ActionExecution:
    row = ActionExecution(**kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _to_dict(r: ActionExecution) -> dict:
    return {
        "id": r.id, "approval_item_id": r.approval_item_id, "agent_id": r.agent_id,
        "action_kind": r.action_kind, "channel": r.channel,
        "target_company": r.target_company, "target_contact": r.target_contact,
        "message": r.message, "status": r.status, "reason": r.reason,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _run_coroutine_blocking(coro: Any, *, timeout: float = 60.0) -> str:
    """Run an async tool from this synchronous, request-scoped code path.

    `asyncio.run` cannot be called from inside the running event loop the API
    endpoint lives in, so the coroutine gets a thread with a loop of its own.
    """
    import asyncio
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=timeout)


def _execute_agent_tool(item: Any, *, tenant: str, base: Dict[str, Any]) -> Dict[str, Any]:
    """Run the tool call an operator just approved."""
    from app.agentic import dispatcher
    from app.agentic.approvals_bridge import payload_of
    from app.agentic.policy import check

    call = payload_of(item)
    with Session(get_engine()) as db:
        if call is None:
            return _to_dict(_record(
                db, **base, action_kind="agent_tool", channel=AGENT_TOOL_CHANNEL,
                status="failed", reason="the approved call could not be read",
            ))

        tool = dispatcher.get(call["name"])
        if tool is None:
            return _to_dict(_record(
                db, **base, action_kind="agent_tool", channel=AGENT_TOOL_CHANNEL,
                status="failed", reason=f"unknown tool: {call['name']}",
            ))

        # The gate again, at the moment of action.
        decision = check(tool.level)
        if decision.verdict == "deny":
            logger.info(
                "approved agent tool refused at execution: %s (%s)",
                call["name"], decision.reason,
            )
            return _to_dict(_record(
                db, **base, action_kind="agent_tool", channel=AGENT_TOOL_CHANNEL,
                status="blocked",
                reason=f"no longer permitted: {decision.reason}",
            ))

        try:
            output = _run_coroutine_blocking(dispatcher.run(call["name"], call["args"]))
        except Exception as exc:  # noqa: BLE001 — a failing command is an outcome
            logger.info("approved agent tool failed: %s: %s", call["name"], exc)
            return _to_dict(_record(
                db, **base, action_kind="agent_tool", channel=AGENT_TOOL_CHANNEL,
                status="failed", reason=str(exc)[:512],
            ))

        logger.info("approved agent tool executed: %s", call["name"])
        return _to_dict(_record(
            db, **base, action_kind="agent_tool", channel=AGENT_TOOL_CHANNEL,
            status="executed", reason=output[:512],
        ))


def execute_for_approval(item: Any, *, tenant_slug: str) -> Dict[str, Any]:
    """Run the action behind an approved item; persist + return the outcome.

    ``item`` is an ApprovalItem (or any object exposing the same attributes).
    Outbound comms are consent-gated; internal actions apply immediately."""
    tenant = (tenant_slug or "default").strip()
    channel = _norm(getattr(item, "channel", ""))
    message = (getattr(item, "proposed_message", "") or getattr(item, "action", ""))[:2048]
    base = dict(
        tenant_slug=tenant, approval_item_id=getattr(item, "id", None),
        agent_id=getattr(item, "agent_id", ""),
        target_company=getattr(item, "target_company", ""), message=message,
    )

    # An agent tool call. Approved by a person, and only now allowed to run — and
    # re-checked against the policy gate first, because an operator who switched
    # shell off after the model asked for it has switched it off, and an approval
    # minted while the door was open is not a key to it.
    if channel == AGENT_TOOL_CHANNEL:
        return _execute_agent_tool(item, tenant=tenant, base=base)

    with Session(get_engine()) as db:
        # internal action — no external recipient, applies immediately
        if channel not in _COMMS:
            row = _record(db, **base, action_kind="internal", channel=channel,
                          status="executed", reason="internal action applied")
            logger.info("action executed (internal) approval=%s", base["approval_item_id"])
            return _to_dict(row)

        # outbound comms — resolve recipient + consent gate (fail-closed)
        email = _resolve_contact_email(db, tenant, base["target_company"])
        if not email:
            row = _record(db, **base, action_kind="message_send", channel=channel,
                          status="blocked", reason="recipient could not be resolved")
            return _to_dict(row)

        gate = check_channel(tenant_slug=tenant, contact_email=email,
                             channel=_GATE_CHANNEL.get(channel, channel))
        if gate.get("allowed"):
            row = _record(db, **base, action_kind="message_send", channel=channel,
                          status="queued", target_contact=email,
                          reason=_REASON_TEXT.get(gate.get("reason", ""), "consent on file · queued"))
            logger.info("action queued (%s) approval=%s → %s", channel, base["approval_item_id"], email)
            return _to_dict(row)

        row = _record(db, **base, action_kind="message_send", channel=channel,
                      status="blocked", target_contact=email,
                      reason=_REASON_TEXT.get(gate.get("reason", ""), gate.get("reason", "no consent")))
        logger.info("action blocked (%s) approval=%s reason=%s",
                    channel, base["approval_item_id"], gate.get("reason"))
        return _to_dict(row)


def list_actions(*, tenant_slug: str, limit: int = 30) -> Dict[str, Any]:
    """Recent outbox entries + status tallies for the Approval Center."""
    tenant = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        rows = list(
            db.exec(
                select(ActionExecution)
                .where(ActionExecution.tenant_slug == tenant)
                .order_by(ActionExecution.created_at.desc())  # type: ignore[attr-defined]
                .limit(limit)
            )
        )
    items = [_to_dict(r) for r in rows]
    tally: Dict[str, int] = {}
    for it in items:
        tally[it["status"]] = tally.get(it["status"], 0) + 1
    return {"items": items, "total": len(items), "by_status": tally}
