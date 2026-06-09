# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Stage F — real metric pipeline.

The Growth Dashboard summary widgets compute from the actual growth records
(companies / contacts / leads / opportunities / consent) instead of reading a
pre-baked agent payload, so the numbers MOVE when the data really changes — a
connector import, a freshly scored lead, a new opportunity. Each function is
pure (Session in → dict out) so it is unit-testable and tenant-scoped.

AEO visibility is the one metric with no local source — it needs an external
answer-engine probe — so it stays sourced from the latest ``aeo_visibility``
agent run, with a graceful neutral fallback when no run exists yet.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.db.growth_models import Company, Contact, Lead, Opportunity

_CURRENCY = {"TRY": "₺", "USD": "$", "EUR": "€", "GBP": "£"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _filled(value) -> bool:
    return bool(value) and str(value).strip() not in ("", "0", "0.0")


# ── CRM hygiene ──────────────────────────────────────────────────────────────
def compute_crm_health(db: Session, tenant: str) -> dict:
    """Data-completeness score across the canonical records. ``fix_suggestions``
    is the real count of missing critical fields — it shrinks as data fills in."""
    companies = list(db.exec(select(Company).where(Company.tenant_slug == tenant)))
    contacts = list(db.exec(select(Contact).where(Contact.tenant_slug == tenant)))
    leads = list(db.exec(select(Lead).where(Lead.tenant_slug == tenant)))

    expected = 0
    present = 0
    fixes = 0

    for c in companies:
        for ok in (_filled(c.domain), _filled(c.sector), _filled(c.vkn)):
            expected += 1
            present += 1 if ok else 0
            fixes += 0 if ok else 1
    for p in contacts:
        for ok in (_filled(p.email), _filled(p.role), _filled(p.consent_status)):
            expected += 1
            present += 1 if ok else 0
            fixes += 0 if ok else 1
    for ln in leads:
        for ok in (ln.score > 0, _filled(ln.source)):
            expected += 1
            present += 1 if ok else 0
            fixes += 0 if ok else 1

    if expected == 0:
        return {"health_pct": None, "fix_suggestions": 0}
    return {"health_pct": round(present / expected * 100), "fix_suggestions": fixes}


# ── Campaign → revenue attribution ───────────────────────────────────────────
def compute_campaign(db: Session, tenant: str) -> dict:
    """Sum opportunity revenue that carries a campaign attribution; the strongest
    channel is the most-attributed campaign. Falls back to total pipeline value
    when nothing is attributed yet."""
    opps = list(db.exec(select(Opportunity).where(Opportunity.tenant_slug == tenant)))
    attributed = [o for o in opps if _filled(o.campaign)]
    revenue_src = attributed or opps

    revenue = round(sum(o.amount for o in revenue_src)) if revenue_src else None
    channel_counts = Counter(o.campaign for o in attributed if _filled(o.campaign))
    top_channel = channel_counts.most_common(1)[0][0] if channel_counts else ""

    cur_code = Counter(o.currency for o in opps).most_common(1)[0][0] if opps else "TRY"
    month = _now().month
    period = f"Q{(month - 1) // 3 + 1}"

    return {
        "attributed_revenue": revenue,
        "currency": _CURRENCY.get(cur_code, cur_code or "₺"),
        "top_channel": top_channel,
        "period": period,
    }


# ── Buying-signal fusion ─────────────────────────────────────────────────────
def compute_buying_signals(db: Session, tenant: str, limit: int = 6) -> dict:
    """Fuse signals from the real records — high-intent leads, fresh
    opportunities, active engagements, entity-resolution merges. ``signal_types``
    is the count of distinct signal kinds actually detected (not a catalog size)."""
    companies = {c.id: c.name for c in db.exec(select(Company).where(Company.tenant_slug == tenant))}
    leads = list(db.exec(select(Lead).where(Lead.tenant_slug == tenant)))
    opps = list(db.exec(select(Opportunity).where(Opportunity.tenant_slug == tenant)))
    cutoff = _now() - timedelta(days=30)

    signals: list[dict] = []

    for ln in sorted(leads, key=lambda x: x.score, reverse=True):
        name = companies.get(ln.company_id, "—")
        if ln.intent == "high":
            signals.append({"icon": "🔥", "label": "Yüksek niyet sinyali", "company": name})
        elif ln.status == "engaged":
            signals.append({"icon": "📈", "label": "Aktif etkileşim", "company": name})

    for o in opps:
        created = o.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created >= cutoff:
            cur = _CURRENCY.get(o.currency, o.currency)
            amt = f" · {round(o.amount):,}{cur}".replace(",", ".") if o.amount else ""
            signals.append({"icon": "🎯", "label": f"Yeni fırsat{amt}", "company": companies.get(o.company_id, "—")})

    for cid, cname in companies.items():
        company = db.get(Company, cid)
        if company and company.merged_count > 1:
            signals.append({"icon": "↻", "label": f"Kayıt füzyonu ×{company.merged_count}", "company": cname})

    signal_types = len({s["icon"] for s in signals})
    return {"signals": signals[:limit], "signal_types": signal_types}


# ── AEO visibility (external probe → agent run) ───────────────────────────────
def aeo_from_payload(payload: dict | None) -> dict:
    """AEO has no local source (needs an answer-engine probe) — read the latest
    ``aeo_visibility`` agent run, neutral fallback when none exists yet."""
    p = payload or {}
    return {
        "visibility_pct": p.get("visibility_pct"),
        "down_categories": p.get("down_categories", 0),
        "categories_total": p.get("categories_total", 8),
    }
