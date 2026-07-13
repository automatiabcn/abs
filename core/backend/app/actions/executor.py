# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Action executor — carry out an approved action, gated by consent (Stage E).

The approval → action bridge. When a reviewer approves an Approval Center item,
this runs its action and records the outcome in the ActionExecution outbox:

  • agent tool calls are re-checked against the policy gate, then dispatched;
  • outbound comms (email / whatsapp / sms / voice) are consent-gated via the
    Consent Ledger (fail-closed) and, when allowed, **actually sent** —
    `app.actions.delivery` reports back whether the message left the building,
    and the outbox row says `sent` or `failed`, never a hopeful `queued`.

No silent sends: outbound never goes out without an opt-in consent record. And no
silent non-sends either: every attempt — sent, blocked or failed — is persisted
with the reason, tenant-scoped, so an operator can see what happened and retry.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from app.actions import delivery
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
        # An internal action — a CRM note, a merge, a field update, a route.
        #
        # This used to write `status="executed", reason="internal action applied"`
        # and change nothing at all. There is no handler for any of them: the only
        # reason this module touches Company or Contact is to look up an email
        # address. So an operator approved a change to their CRM, the outbox told
        # them it had been applied, and their data was exactly as before.
        #
        # Until a handler exists, say so. An approval that cannot be carried out is
        # a failure, and a failure a person can see is worth more than a success
        # they cannot.
        if channel not in _COMMS:
            row = _record(db, **base, action_kind="internal", channel=channel,
                          status="failed",
                          reason=(f"no handler for '{channel}' actions on this server "
                                  "— nothing was changed"))
            logger.warning(
                "approved internal action has no handler: channel=%s approval=%s",
                channel, base["approval_item_id"],
            )
            return _to_dict(row)

        # outbound comms — resolve recipient + consent gate (fail-closed)
        email = _resolve_contact_email(db, tenant, base["target_company"])
        if not email:
            row = _record(db, **base, action_kind="message_send", channel=channel,
                          status="blocked", reason="recipient could not be resolved")
            return _to_dict(row)

        gate = check_channel(tenant_slug=tenant, contact_email=email,
                             channel=_GATE_CHANNEL.get(channel, channel))
        if not gate.get("allowed"):
            row = _record(db, **base, action_kind="message_send", channel=channel,
                          status="blocked", target_contact=email,
                          reason=_REASON_TEXT.get(gate.get("reason", ""), gate.get("reason", "no consent")))
            logger.info("action blocked (%s) approval=%s reason=%s",
                        channel, base["approval_item_id"], gate.get("reason"))
            return _to_dict(row)

        # A person approved it and the Consent Ledger allows it. Send it.
        #
        # It used to stop here and write `status="queued"` — into a queue nothing
        # drains, in a codebase with no worker and no `where(status == "queued")`
        # anywhere in it. The message never went. This is where it goes.
        result = delivery.deliver(
            channel=channel,
            to=email,
            subject=_subject_for(item, base["target_company"]),
            message=message,
        )
        row = _record(
            db, **base, action_kind="message_send", channel=channel,
            target_contact=email,
            status="sent" if result.sent else "failed",
            reason=result.detail[:256],
        )
        logger.info(
            "action %s (%s) approval=%s → %s: %s",
            "sent" if result.sent else "FAILED", channel,
            base["approval_item_id"], email, result.detail,
        )
        return _to_dict(row)


def _subject_for(item: Any, company: str) -> str:
    """A subject line for an approved outbound email."""
    subject = (getattr(item, "subject", "") or "").strip()
    if subject:
        return subject[:200]
    title = (getattr(item, "title", "") or "").strip()
    if title:
        return title[:200]
    return f"Message from {company}"[:200] if company else "Message"


class RetryNotAllowed(Exception):
    """The outbox row cannot be retried, and why."""


def retry_action(*, tenant_slug: str, action_id: int) -> Dict[str, Any]:
    """Send a failed outbound message again.

    An SMTP server that was down for a minute should not cost an operator the
    message they approved. A failed row keeps everything needed to send it —
    recipient, body, channel — so this re-runs the consent gate (it may have been
    withdrawn since) and the delivery, and updates the row with what happened.

    Only `failed` message_send rows. A `sent` row is not retried, because sending
    it twice is a second message to a real person, and a `blocked` row was refused
    on purpose."""
    tenant = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        row = db.get(ActionExecution, action_id)
        if row is None or row.tenant_slug != tenant:
            raise KeyError("action_not_found")
        if row.action_kind != "message_send":
            raise RetryNotAllowed("only an outbound message can be retried")
        if row.status != "failed":
            raise RetryNotAllowed(f"this message is '{row.status}', not failed — nothing to retry")

        gate = check_channel(
            tenant_slug=tenant, contact_email=row.target_contact,
            channel=_GATE_CHANNEL.get(row.channel, row.channel),
        )
        if not gate.get("allowed"):
            row.status = "blocked"
            row.reason = _REASON_TEXT.get(
                gate.get("reason", ""), gate.get("reason", "no consent")
            )[:256]
        else:
            result = delivery.deliver(
                channel=row.channel, to=row.target_contact,
                subject=_subject_for(None, row.target_company), message=row.message,
            )
            row.status = "sent" if result.sent else "failed"
            row.reason = result.detail[:256]

        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info("outbox retry: id=%s → %s (%s)", action_id, row.status, row.reason)
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
