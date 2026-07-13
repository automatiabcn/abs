# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Inbound triage orchestration over the Agent Runtime + Approval Center."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.agents.runtime import run_agent

logger = logging.getLogger(__name__)

# Intent taxonomy (design doc §7.9).
INTENTS = [
    "sales_inquiry",
    "pricing_request",
    "demo_request",
    "support_request",
    "complaint",
    "partnership",
    "vendor_message",
    "job_application",
    "spam",
    "urgent_customer_issue",
]


async def triage_inbound(
    message: str,
    *,
    tenant_slug: str,
    channel: str = "web",
    from_email: str = "",
    project_slug: Optional[str] = None,
    actor: str = "",
) -> Dict[str, Any]:
    """Classify an inbound request + draft a source-cited reply.

    Runs the Inbound Triage Agent (RAG-grounded), extracts the intent, logs the
    run and — because the draft is medium-risk — opens an Approval Center item.
    Returns the structured triage result for the Inbound Intelligence UI.
    """
    task = (
        "Classify this inbound customer request and draft a reply that CITES its "
        "sources from the company knowledge base. Put EXACTLY one of these values "
        f"in JSON payload.intent: {', '.join(INTENTS)}. "
        "Put the reply draft in payload.draft.\n\nREQUEST: " + (message or "")
    )
    res = await run_agent(
        "inbound_triage",
        task,
        tenant_id=tenant_slug,
        project_slug=project_slug,
        user_subject=actor,
    )

    payload = res.payload if isinstance(res.payload, dict) else {}
    intent = str(payload.get("intent") or "").strip().lower()
    if intent not in INTENTS:
        intent = "sales_inquiry"
    draft = str(payload.get("draft") or res.recommended_action or "").strip()

    # Consent gate: the reply goes back to the sender by email — record whether
    # we actually have consent for that channel so the reviewer sees it.
    consent_status = ""
    if from_email:
        try:
            from app.consent import check_channel

            g = check_channel(
                tenant_slug=tenant_slug, contact_email=from_email, channel="email"
            )
            consent_status = g.get("status", "") or (
                "opt-in" if g.get("allowed") else "unknown"
            )
        except Exception:  # noqa: BLE001 — best-effort
            consent_status = ""

    run_id: Optional[int] = None
    approval: Optional[dict] = None
    try:
        from app.approvals import create_approval_from_result, log_agent_run

        run_id = log_agent_run(res, tenant_slug=tenant_slug, actor=actor, task=message)
        if res.requires_approval:
            approval = create_approval_from_result(
                res,
                tenant_slug=tenant_slug,
                requester=actor or from_email,
                agent_run_id=run_id,
                channel=channel,
                target_person=from_email,
                consent_status=consent_status,
            )
    except Exception:  # noqa: BLE001 — persistence best-effort
        logger.info("inbound persistence skipped", exc_info=True)

    return {
        "intent": intent,
        "draft": draft,
        "summary": res.summary,
        "citations": [e.to_dict() for e in res.evidence],
        "confidence": res.confidence,
        "requires_approval": res.requires_approval,
        "run_id": run_id,
        "approval": approval,
    }
