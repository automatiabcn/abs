# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Agentic Growth — demo seed.

Populates the growth tables (companies / contacts / leads / agent_runs /
approval_items / connector_states / consent_records) with a realistic sample
set so every Agentic Growth screen renders the "complete" experience shown in
the mockups instead of an empty state. Idempotent: a second call is a no-op
once the sentinel company exists. Gated to demo deployments by the caller.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.db.growth_models import (
    Company,
    ConnectorState,
    ConsentRecord,
    Contact,
    Lead,
    Opportunity,
    WorkflowRun,
)
from app.db.models import AgentRun, ApprovalItem
from app.db.session import get_engine


def _consent_flags(status: str) -> dict | None:
    """Map a contact's consent label → Consent Ledger channel flags.

    Drives the Stage E action gate: 'opt-in' → all channels; 'partial' → email
    only; 'opt-out' → none (opted out); blank → no record (fail-closed)."""
    s = (status or "").strip().lower()
    if not s:
        return None
    if "opt-out" in s:
        return {
            "email_consent": False,
            "phone_consent": False,
            "sms_consent": False,
            "whatsapp_consent": False,
            "legal_basis": "",
            "opted_out": True,
        }
    if "partial" in s:
        return {
            "email_consent": True,
            "phone_consent": False,
            "sms_consent": False,
            "whatsapp_consent": False,
            "legal_basis": "legitimate_interest",
            "opted_out": False,
        }
    return {
        "email_consent": True,
        "phone_consent": True,
        "sms_consent": True,
        "whatsapp_consent": True,
        "legal_basis": "consent",
        "opted_out": False,
    }


logger = logging.getLogger(__name__)

_SENTINEL = "Northgate Construction Ltd."


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Company, sector, lead score/intent/consent, recommended_action, score breakdown.
_COMPANIES = [
    {
        "name": "Northgate Construction Ltd.",
        "sector": "Construction",
        "score": 0.87,
        "intent": "high",
        "consent": "opt-in",
        "vkn": "1234567890",
        "domain": "northgate-construction.com",
        "evidence": [
            "Pricing page visited 3x",
            "Job postings +4 (procurement)",
            "Repeat order in ERP",
        ],
        "merged_count": 3,
        "match_confidence": 0.96,
        "lifecycle": "customer",
        "opportunities": [
            {
                "name": "window systems project",
                "stage": "proposal",
                "amount": 420000,
                "campaign": "Meta Ads · Q2",
            },
            {
                "name": "Prior quote",
                "stage": "closed_won",
                "amount": 180000,
                "campaign": "",
            },
        ],
        "score_criteria": {
            "ICP fit": 0.92,
            "Purchase likelihood": 0.84,
            "Budget potential": 0.78,
            "Intent signal": 0.90,
            "Service need": 0.81,
            "CRM history": 0.70,
            "ERP history (repeat purchase)": 0.88,
            "Timing fit": 0.86,
            "Contact consent": 1.0,
            "Data confidence": 0.96,
        },
        "lead_evidence": [
            {
                "kind": "rag",
                "ref": "Quote to a comparable past customer · proposal-archive",
            },
            {
                "kind": "graph",
                "ref": "Account→2 Opportunity · $420K invoiced previously (ERP)",
            },
            {"kind": "signal", "ref": "Pricing page visit + job postings up (+4)"},
        ],
        "buying_group": [
            {"name": "M. Harding", "role": "decision_maker"},
            {"name": "Finance Approver", "role": "finance_approver"},
            {"name": "Technical Evaluator 1", "role": "technical_evaluator"},
            {"name": "Assistant", "role": "gatekeeper"},
        ],
    },
    {
        "name": "Stonebridge Builders",
        "sector": "Construction",
        "score": 0.64,
        "intent": "medium",
        "consent": "opt-in",
        "vkn": "2345678901",
        "domain": "stonebridgebuilders.com",
        "evidence": ["Pricing page visit", "LinkedIn engagement"],
    },
    {
        "name": "Technova Engineering",
        "sector": "Manufacturing",
        "score": 0.58,
        "intent": "medium",
        "consent": "partial",
        "vkn": "3456789012",
        "domain": "technova-eng.com",
        "evidence": ["Demo form #2841", "Web crawl: new product line"],
    },
    {
        "name": "Bluewave Logistics",
        "sector": "Logistics",
        "score": 0.31,
        "intent": "watching",
        "consent": "opt-out",
        "vkn": "4567890123",
        "domain": "bluewavelogistics.com",
        "evidence": ["New location opening"],
    },
    {
        "name": "Technova Group",
        "sector": "Manufacturing",
        "score": 0.52,
        "intent": "medium",
        "consent": "opt-in",
        "vkn": "5678901234",
        "domain": "technova-group.com",
        "evidence": ["Job postings up +4", "Sector report match"],
    },
]

# Activity feed — (agent_id, summary, risk, requires_approval, minutes_ago, confidence, payload).
# `payload` carries the structured result the dashboard summary widgets read
# (latest run per agent), so AEO / campaign / CRM / signals are data-derived
# rather than hardcoded in the dashboard service.
_RUNS = [
    (
        "lead_discovery",
        "Found 12 new ICP-matching companies in the region · queued for enrichment",
        "low",
        False,
        2,
        0.0,
        {},
    ),
    (
        "lead_scoring",
        '"Northgate Construction Ltd." scored → 0.87 (high) · 14 pieces of evidence · top-3 RAG sources attached',
        "medium",
        False,
        5,
        0.87,
        {},
    ),
    (
        "inbound_triage",
        'Classified an inbound request → "pricing_request" · reply draft + CRM note generated',
        "medium",
        True,
        8,
        0.79,
        {"intent": "pricing_request"},
    ),
    (
        "competitive_intel",
        "Caught a competitor price change · Battlecard Agent triggered",
        "low",
        False,
        14,
        0.0,
        {},
    ),
    (
        "aeo_visibility",
        "Detected a visibility drop in 2 categories of AI answers · content-gap report generated",
        "low",
        False,
        22,
        0.0,
        {
            "visibility_pct": 41,
            "down_categories": 2,
            "categories_total": 8,
            "recommended": 3,
        },
    ),
    (
        "buying_signal",
        "Scanned 16 signal types · fused 5 new buying signals",
        "low",
        False,
        28,
        0.0,
        {
            "signals": [
                {
                    "icon": "🔥",
                    "label": "Pricing page visit",
                    "company": "Stonebridge Builders",
                },
                {
                    "icon": "📈",
                    "label": "Job postings up +4",
                    "company": "Technova Group",
                },
                {"icon": "🎯", "label": "Demo request", "company": "Form #2841"},
                {
                    "icon": "🏢",
                    "label": "New location",
                    "company": "Bluewave Logistics",
                },
                {
                    "icon": "↻",
                    "label": "Repeat purchase",
                    "company": "ERP · 3 customers",
                },
            ],
            "signal_types": 16,
        },
    ),
    (
        "campaign_attribution",
        "campaign → revenue mapping · Meta Ads converts best · ERP-verified",
        "medium",
        False,
        35,
        0.0,
        {
            "attributed_revenue": 1240000,
            "currency": "$",
            "top_channel": "Meta Ads",
            "period": "Q2",
        },
    ),
    (
        "crm_hygiene",
        "Scanned the CRM · 11 suggested fixes (duplicates + missing fields)",
        "medium",
        False,
        45,
        0.0,
        {"health_pct": 86, "fix_suggestions": 11},
    ),
]

# Pending approvals. The first two are detailed cards; the rest populate the
# "queue (5 more)" table. `evidence` items are {kind, ref} so the card can split
# EVIDENCE·RAG / EVIDENCE·GRAPH / CONSENT / POLICY.
_APPROVALS = [
    {
        "agent_id": "inbound_triage",
        "risk": "medium",
        "consent": "opt-in",
        "policy": "requires_approval",
        "company": "Northgate Construction Ltd.",
        "channel": "email",
        "mins": 8,
        "action": 'Cited reply draft for the "Northgate Construction Ltd." pricing request → send email + CRM note',
        "rationale": 'The inbound request was classified "pricing_request" (0.94 confidence). The customer matches the ICP and has received 2 quotes before. Drafted from the standard pricing policy plus quote history for comparable customers.',
        "message": "Hello, thanks for reaching out. Attached are our price range for the premium series [1] and the installation process [2]. We can propose a solution close to the one from your previous project…",
        "evidence": [
            {"kind": "rag", "ref": "[1] pricing-policy.pdf"},
            {"kind": "rag", "ref": "[2] installation-process.docx"},
            {"kind": "graph", "ref": "Account→2 Opportunity prior quote"},
        ],
    },
    {
        "agent_id": "outbound_draft",
        "risk": "high",
        "consent": "opt-in",
        "policy": "requires approval + audit",
        "company": "Stonebridge Builders",
        "channel": "email",
        "mins": 21,
        "action": 'Outbound email to the "Stonebridge Builders" decision maker (buying signal: pricing page visit)',
        "rationale": "Lead score 0.81. Pricing page visit plus a rise in job postings. Consent verified in the consent registry, opt-in source: web form. Domain reputation is healthy, bounce rate 0.4%.",
        "message": "Hello, may I summarise our solutions for your construction projects in 2 minutes?",
        "evidence": [
            {"kind": "consent", "ref": "email consent · registered 2026-03"},
            {"kind": "policy", "ref": "requires approval + audit"},
        ],
    },
    # ── queue (5 more) ──
    {
        "agent_id": "crm_hygiene",
        "risk": "medium",
        "consent": "",
        "policy": "approval",
        "company": "",
        "channel": "",
        "mins": 30,
        "action": "Merge 11 duplicates",
        "rationale": "",
        "message": "",
        "evidence": [],
    },
    {
        "agent_id": "campaign_attribution",
        "risk": "medium",
        "consent": "",
        "policy": "approval",
        "company": "",
        "channel": "",
        "mins": 40,
        "action": "Update CRM opportunity fields",
        "rationale": "",
        "message": "",
        "evidence": [],
    },
    {
        "agent_id": "social_strategy",
        "risk": "medium",
        "consent": "",
        "policy": "approval",
        "company": "",
        "channel": "",
        "mins": 52,
        "action": "Ad audience suggestion",
        "rationale": "",
        "message": "",
        "evidence": [],
    },
    {
        "agent_id": "voice_call",
        "risk": "high",
        "consent": "partial",
        "policy": "consent check",
        "company": "Technova Engineering",
        "channel": "voice",
        "mins": 64,
        "action": "Outbound call suggestion (10 leads)",
        "rationale": "",
        "message": "",
        "evidence": [],
    },
    {
        "agent_id": "outbound_draft",
        "risk": "high",
        "consent": "opt-in",
        "policy": "approval+audit",
        "company": "Bluewave Logistics",
        "channel": "whatsapp",
        "mins": 75,
        "action": "WhatsApp template message",
        "rationale": "",
        "message": "",
        "evidence": [],
    },
]

_CONNECTORS = ["parasut", "hubspot", "gmail"]

# Workflow run history — (name, trigger, step_count, status, approvals, elapsed_ms, mins_ago).
_WORKFLOW_RUNS = [
    ("Inbound → Reply Draft", "web form", 7, "done", 1, 4200, 12),
    ("Inbound → Reply Draft", "email", 7, "partial", 1, 2100, 34),
    ("Inbound → Reply Draft", "WhatsApp", 7, "done", 0, 5000, 58),
]


def _already_seeded(db: Session, tenant: str) -> bool:
    return (
        db.exec(
            select(Company).where(
                Company.tenant_slug == tenant, Company.name == _SENTINEL
            )
        ).first()
        is not None
    )


def seed_growth_demo(tenant_slug: str = "default", *, force: bool = False) -> dict:
    """Idempotently insert the demo growth dataset. Returns a small summary."""
    tenant = (tenant_slug or "default").strip() or "default"
    now = _now()
    created = {
        "companies": 0,
        "leads": 0,
        "runs": 0,
        "approvals": 0,
        "connectors": 0,
        "contacts": 0,
    }

    with Session(get_engine()) as db:
        if not force and _already_seeded(db, tenant):
            return {"ok": True, "skipped": "already_seeded", **created}

        run_id_by_agent: dict[str, int] = {}

        # Companies + leads + a primary contact each.
        for c in _COMPANIES:
            company = Company(
                tenant_slug=tenant,
                name=c["name"],
                sector=c["sector"],
                vkn=c.get("vkn", ""),
                domain=c.get("domain", ""),
                score=c["score"],
                lifecycle=c.get("lifecycle", "lead"),
                merged_count=c.get("merged_count", 1),
                match_confidence=c.get("match_confidence", 0.93),
                source="erp+crm+web",
            )
            db.add(company)
            db.commit()
            db.refresh(company)
            created["companies"] += 1

            for op in c.get("opportunities", []):
                db.add(
                    Opportunity(
                        tenant_slug=tenant,
                        company_id=company.id,
                        name=op["name"],
                        stage=op["stage"],
                        amount=op["amount"],
                        currency="USD",
                        campaign=op.get("campaign", ""),
                    )
                )
            db.commit()

            # Buying group: a rich set for the flagship lead, else one contact.
            bg = c.get("buying_group") or [
                {"name": f"{c['name'].split()[0]} Buyer", "role": "purchasing"}
            ]
            flags = _consent_flags(c["consent"])
            for member in bg:
                email = f"{member['role']}@{c.get('domain', 'example.com')}"
                db.add(
                    Contact(
                        tenant_slug=tenant,
                        company_id=company.id,
                        name=member["name"],
                        email=email,
                        role=member["role"],
                        consent_status=c["consent"],
                    )
                )
                created["contacts"] += 1
                # Consent Ledger record (Stage E action gate). Absent = fail-closed.
                if flags is not None:
                    opted_out = flags.pop("opted_out", False)
                    db.add(
                        ConsentRecord(
                            tenant_slug=tenant,
                            contact_email=email,
                            email_consent=flags["email_consent"],
                            phone_consent=flags["phone_consent"],
                            sms_consent=flags["sms_consent"],
                            whatsapp_consent=flags["whatsapp_consent"],
                            legal_basis=flags["legal_basis"],
                            opt_in_source="import",
                            opt_in_at=None if opted_out else now,
                            opt_out_at=now if opted_out else None,
                        )
                    )
                    flags["opted_out"] = opted_out  # restore for next contact iter

            score_json = json.dumps(
                c.get("score_criteria")
                or {"icp_fit": c["score"], "buying_signal": c["score"]},
                ensure_ascii=False,
            )
            evidence_json = json.dumps(
                c.get("lead_evidence") or c["evidence"], ensure_ascii=False
            )
            lead = Lead(
                tenant_slug=tenant,
                company_id=company.id,
                source="erp+crm+web",
                intent=c["intent"],
                score=c["score"],
                status="scored",
                consent_status=c["consent"],
                score_json=score_json,
                evidence_json=evidence_json,
            )
            db.add(lead)
            created["leads"] += 1
        db.commit()

        # Activity feed (agent_runs) — staggered timestamps.
        for agent_id, summary, risk, needs_approval, mins, conf, payload in _RUNS:
            run = AgentRun(
                tenant_slug=tenant,
                agent_id=agent_id,
                task="(demo seed)",
                summary=summary,
                confidence=conf,
                risk=risk,
                requires_approval=needs_approval,
                provider="gpt-oss-120b",
                payload_json=json.dumps(payload, ensure_ascii=False),
                created_at=now - timedelta(minutes=mins),
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            run_id_by_agent.setdefault(agent_id, run.id)
            created["runs"] += 1

        # Pending approvals (detailed cards + queue).
        for ap in _APPROVALS:
            db.add(
                ApprovalItem(
                    tenant_slug=tenant,
                    agent_id=ap["agent_id"],
                    agent_run_id=run_id_by_agent.get(ap["agent_id"]),
                    action=ap["action"],
                    target_company=ap["company"],
                    channel=ap["channel"],
                    rationale=ap["rationale"],
                    risk=ap["risk"],
                    consent_status=ap["consent"],
                    proposed_message=ap["message"],
                    evidence_json=json.dumps(ap["evidence"], ensure_ascii=False),
                    policy_result=ap["policy"],
                    status="pending",
                    created_at=now - timedelta(minutes=ap["mins"]),
                )
            )
            created["approvals"] += 1
        db.commit()

        # Workflow run history.
        for name, trigger, sc, st, ap, ms, mins in _WORKFLOW_RUNS:
            db.add(
                WorkflowRun(
                    tenant_slug=tenant,
                    name=name,
                    trigger=trigger,
                    steps_json=json.dumps(["inbound_triage", "knowledge_base"]),
                    status=st,
                    step_count=sc,
                    approvals_opened=ap,
                    elapsed_ms=ms,
                    created_at=now - timedelta(minutes=mins),
                )
            )
        db.commit()

        # Connector states.
        for cid in _CONNECTORS:
            existing = db.exec(
                select(ConnectorState).where(
                    ConnectorState.tenant_slug == tenant,
                    ConnectorState.connector_id == cid,
                )
            ).first()
            if not existing:
                db.add(
                    ConnectorState(
                        tenant_slug=tenant,
                        connector_id=cid,
                        status="connected",
                        health=100 if cid != "gmail" else 82,
                        connected_at=now - timedelta(days=3),
                        last_sync_at=now - timedelta(minutes=12),
                    )
                )
                created["connectors"] += 1
        db.commit()

    logger.info("growth demo seeded tenant=%s %s", tenant, created)
    return {"ok": True, **created}
