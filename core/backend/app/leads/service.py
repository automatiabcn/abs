# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Lead Intelligence service — CRUD + Lead Scoring Agent → persisted score.

All operations tenant-scoped (``WHERE tenant_slug``); RLS (0021) is the DB-tier
net. Scoring runs the Lead Scoring Agent over the company context and persists
the score + 15-criterion breakdown + evidence onto the lead.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.db.growth_models import Company, Contact, Lead
from app.db.session import get_engine

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _intent_from_score(score: float) -> str:
    return "high" if score >= 0.8 else ("medium" if score >= 0.65 else "watching")


def _recommended_action(intent: str, consent_status: str) -> str:
    """Mirrors the Lead Intelligence screen's "Önerilen aksiyon" column."""
    if consent_status == "opt-out" or consent_status == "" and intent == "watching":
        return "Sadece iç-görev"
    if intent == "high":
        return "Inbound cevap taslağı"
    if intent == "medium":
        return "Outbound öneri (onay)" if consent_status in ("opt-in", "izinli") else "Enrichment gerekli"
    return "Nurture"


def create_company(*, tenant_slug: str, name: str, **fields: Any) -> int:
    row = Company(tenant_slug=(tenant_slug or "default"), name=name[:256], **{
        k: v for k, v in fields.items() if hasattr(Company, k)
    })
    with Session(get_engine()) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)


def create_lead(
    *, tenant_slug: str, company_id: Optional[int] = None, source: str = "",
    owner: str = "", consent_status: str = "",
) -> dict:
    row = Lead(
        tenant_slug=(tenant_slug or "default"), company_id=company_id,
        source=source[:64], owner=owner[:254], consent_status=consent_status[:32],
        status="new",
    )
    with Session(get_engine()) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        return _lead_dict(row, db)


def _lead_dict(r: Lead, db: Session) -> dict:
    company = db.get(Company, r.company_id) if r.company_id else None
    bg_count = 0
    if r.company_id:
        bg_count = len(db.exec(
            select(Contact).where(
                Contact.tenant_slug == r.tenant_slug, Contact.company_id == r.company_id
            )
        ).all())
    return {
        "id": r.id,
        "company_id": r.company_id,
        "company_name": company.name if company else "",
        "sector": company.sector if company else "",
        "buying_group_count": bg_count,
        "source": r.source,
        "intent": r.intent,
        "score": round(r.score, 3),
        "score_breakdown": json.loads(r.score_json or "{}"),
        "evidence": json.loads(r.evidence_json or "[]"),
        "status": r.status,
        "owner": r.owner,
        "consent_status": r.consent_status,
        "recommended_action": _recommended_action(r.intent, r.consent_status),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _buying_group(db: Session, *, tenant_slug: str, company_id: Optional[int]) -> List[dict]:
    """Contacts at the company grouped by role (Lead detail buying group)."""
    if not company_id:
        return []
    rows = list(
        db.exec(select(Contact).where(
            Contact.tenant_slug == tenant_slug, Contact.company_id == company_id,
        ))
    )
    return [{"name": c.name, "role": c.role or "contact",
             "consent_status": c.consent_status} for c in rows]


async def score_lead(*, tenant_slug: str, lead_id: int, actor: str = "") -> Optional[dict]:
    """Run the Lead Scoring Agent over the lead's company → persist score."""
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        lead = db.get(Lead, lead_id)
        if lead is None or lead.tenant_slug != tenant_slug:
            return None
        company = db.get(Company, lead.company_id) if lead.company_id else None
        company_name = company.name if company else "(bilinmeyen firma)"
        sector = company.sector if company else ""

    from app.agents.runtime import run_agent

    task = (
        f"Şu firmayı 15 kritere göre skorla (0..1). JSON payload.score (0..1) ve "
        f"payload.criteria (kriter→0..1 sözlüğü) döndür. Firma: {company_name} "
        f"(sektör: {sector or 'bilinmiyor'})."
    )
    res = await run_agent(
        "lead_scoring", task, tenant_id=tenant_slug, user_subject=actor
    )
    payload = res.payload if isinstance(res.payload, dict) else {}
    # criteria: explicit "criteria" dict, else any numeric-valued sub-dict.
    criteria = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {}
    if not criteria:
        nums = {k: v for k, v in payload.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1}
        if len(nums) >= 3:
            criteria = nums
    # score: explicit payload.score, else mean of criteria, else agent confidence.
    score: float
    try:
        score = float(payload.get("score"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        crit_vals = [float(v) for v in criteria.values()
                     if isinstance(v, (int, float)) and not isinstance(v, bool)]
        score = (sum(crit_vals) / len(crit_vals)) if crit_vals else res.confidence
    score = max(0.0, min(1.0, score))

    with Session(get_engine()) as db:
        lead = db.get(Lead, lead_id)
        if lead is None or lead.tenant_slug != tenant_slug:
            return None
        lead.score = score
        lead.intent = _intent_from_score(score)
        lead.score_json = json.dumps(criteria)[:65000]
        lead.evidence_json = json.dumps([e.to_dict() for e in res.evidence])[:65000]
        lead.status = "scored"
        lead.updated_at = _now()
        db.add(lead)
        db.commit()
        db.refresh(lead)
        out = _lead_dict(lead, db)
    # log the scoring run (best-effort)
    try:
        from app.approvals import log_agent_run
        log_agent_run(res, tenant_slug=tenant_slug, actor=actor, task=task)
    except Exception:  # noqa: BLE001
        logger.info("lead score run log skipped", exc_info=True)
    return out


def list_leads(*, tenant_slug: str, limit: int = 100) -> Dict[str, Any]:
    """Account-priority list (score desc) for the Lead Intelligence screen."""
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        rows = list(
            db.exec(
                select(Lead).where(Lead.tenant_slug == tenant_slug)
                .order_by(Lead.score.desc()).limit(limit)
            )
        )
        items = [_lead_dict(r, db) for r in rows]
    return {"items": items, "total": len(items)}


def get_lead(*, tenant_slug: str, lead_id: int) -> Optional[dict]:
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        row = db.get(Lead, lead_id)
        if row is None or row.tenant_slug != tenant_slug:
            return None
        out = _lead_dict(row, db)
        out["buying_group"] = _buying_group(
            db, tenant_slug=tenant_slug, company_id=row.company_id
        )
        return out
