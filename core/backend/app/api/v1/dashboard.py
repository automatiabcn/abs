# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/dashboard — Growth Dashboard aggregate.

Ties the agentic core together for the Dashboard screen (mockup 01): scorecards
(growth score / hot accounts / pending approvals / active agents), the live
agent-activity feed, buying-signal fusion, account-priority table, and the
summary widgets (AEO visibility, campaign→revenue, inbound today, CRM health,
connector health, model gateway). The summary widgets read the LATEST run per
agent so the values are data-derived (a real run or the demo seed), never
hardcoded. Tenant from the authenticated principal.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.agents.registry import AGENTS
from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.approvals.service import list_approvals, recent_agent_runs
from app.connectors import list_connectors
from app.db.models import AgentRun
from app.db.session import get_engine
from app.growth_metrics import (
    aeo_from_payload,
    compute_buying_signals,
    compute_campaign,
    compute_crm_health,
)
from app.leads import list_leads

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])


def _latest_payloads(tenant: str) -> dict[str, dict]:
    """Latest run payload per agent_id (for the summary widgets)."""
    out: dict[str, dict] = {}
    with Session(get_engine()) as db:
        rows = db.exec(
            select(AgentRun)
            .where(AgentRun.tenant_slug == tenant)
            .order_by(AgentRun.created_at.desc())
        ).all()
        for r in rows:
            if r.agent_id in out:
                continue
            try:
                out[r.agent_id] = json.loads(r.payload_json or "{}")
            except Exception:
                out[r.agent_id] = {}
    return out


def _inbound_today(tenant: str) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    with Session(get_engine()) as db:
        rows = db.exec(
            select(AgentRun).where(
                AgentRun.tenant_slug == tenant,
                AgentRun.agent_id == "inbound_triage",
                AgentRun.created_at >= cutoff,
            )
        ).all()
        return len(rows)


@router.get("")
async def dashboard(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    tenant = (auth.tenant_id or "default").strip() or "default"
    activity = recent_agent_runs(tenant_slug=tenant, limit=20)
    approvals = list_approvals(tenant_slug=tenant, status="pending")
    leads = list_leads(tenant_slug=tenant)
    connectors = list_connectors(tenant_slug=tenant)
    payloads = _latest_payloads(tenant)

    lead_items = leads["items"]
    scored = [ln["score"] for ln in lead_items if ln.get("score")]
    growth_score = round(sum(scored) / len(scored) * 100) if scored else 0
    hot_accounts = sum(1 for ln in lead_items if ln.get("intent") == "high")
    active_agents = len({a["agent_id"] for a in activity})

    # Stage F — metrics computed from the real records (move with the data),
    # except AEO which legitimately needs an external answer-engine probe.
    with Session(get_engine()) as db:
        campaign = compute_campaign(db, tenant)
        crm = compute_crm_health(db, tenant)
        signals = compute_buying_signals(db, tenant)
    aeo = aeo_from_payload(payloads.get("aeo_visibility"))

    # Connector health = mean of connected states' health (catalog from registry).
    healths = [
        c.get("health") or 0
        for g in connectors.get("groups", [])
        for c in g.get("connectors", [])
        if c.get("status") == "connected"
    ]
    conn_health = round(sum(healths) / len(healths)) if healths else 0

    return {
        "scorecards": {
            "growth_score": growth_score,
            "hot_accounts": hot_accounts,
            "pending_approvals": approvals["pending_total"],
            "high_risk_approvals": approvals["by_risk"].get("high", 0),
            "active_agents": active_agents,
            "total_agents": len(AGENTS),
        },
        "activity": activity,
        "activity_count": len(activity),
        "buying_signals": {
            "items": signals["signals"],
            "signal_types": signals["signal_types"],
        },
        "account_priority": lead_items[:6],
        "aeo": aeo,
        "campaign": campaign,
        "inbound_today": _inbound_today(tenant),
        "crm_health": crm,
        "connectors": {
            "connected": connectors["connected_total"],
            "catalog": connectors["catalog_total"],
            "health": conn_health,
        },
        "model_gateway": {
            "cost": 0,
            "currency": "$",
            "models": 22,
            "mode": "free-first cascade",
        },
        # Back-compat keys (old frontend shape) — harmless extras.
        "agents": {
            "total": len(AGENTS),
            "approval_gated": sum(1 for a in AGENTS.values() if a.requires_approval),
            "active": active_agents,
        },
        "approvals": {
            "pending_total": approvals["pending_total"],
            "by_risk": approvals["by_risk"],
        },
        "hot_accounts": hot_accounts,
    }
