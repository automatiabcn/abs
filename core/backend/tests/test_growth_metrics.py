# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Stage F — real metric pipeline unit tests.

Each test uses an isolated tenant slug and asserts the metric is computed from
the actual records (and moves when the data changes), never a fixed payload.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app.db.growth_models import Company, Contact, Lead, Opportunity
from app.db.session import get_engine
from app.growth_metrics import (
    aeo_from_payload,
    compute_buying_signals,
    compute_campaign,
    compute_crm_health,
)


def _seed_company(db: Session, tenant: str, **kw) -> Company:
    c = Company(tenant_slug=tenant, name=kw.pop("name", "Acme"), **kw)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ── CRM health ───────────────────────────────────────────────────────────────
def test_crm_health_none_when_empty():
    with Session(get_engine()) as db:
        out = compute_crm_health(db, "t_crm_empty")
    assert out == {"health_pct": None, "fix_suggestions": 0}


def test_crm_health_complete_is_100_no_fixes():
    t = "t_crm_full"
    with Session(get_engine()) as db:
        c = _seed_company(
            db, t, name="Tam A.Ş.", domain="tam.com", sector="İnşaat", vkn="1234567890"
        )
        db.add(
            Contact(
                tenant_slug=t,
                company_id=c.id,
                name="Ali",
                email="ali@tam.com",
                role="decision_maker",
                consent_status="opt-in",
            )
        )
        db.add(
            Lead(tenant_slug=t, company_id=c.id, source="erp", score=0.8, intent="high")
        )
        db.commit()
        out = compute_crm_health(db, t)
    assert out["health_pct"] == 100
    assert out["fix_suggestions"] == 0


def test_crm_health_counts_missing_fields():
    t = "t_crm_gaps"
    with Session(get_engine()) as db:
        # company missing domain + vkn (2 gaps), contact missing role + consent (2),
        # lead missing score + source (2) → 6 gaps of 8 fields → 25% filled.
        c = _seed_company(db, t, name="Eksik Ltd", sector="Üretim")
        db.add(
            Contact(tenant_slug=t, company_id=c.id, name="Veli", email="veli@eksik.com")
        )
        db.add(Lead(tenant_slug=t, company_id=c.id, score=0.0))
        db.commit()
        out = compute_crm_health(db, t)
    assert out["fix_suggestions"] == 6
    assert 0 < out["health_pct"] < 100


# ── Campaign attribution ─────────────────────────────────────────────────────
def test_campaign_none_when_no_opportunities():
    with Session(get_engine()) as db:
        out = compute_campaign(db, "t_camp_empty")
    assert out["attributed_revenue"] is None
    assert out["top_channel"] == ""


def test_campaign_sums_attributed_and_picks_top_channel():
    t = "t_camp_real"
    with Session(get_engine()) as db:
        c = _seed_company(db, t, name="Gelir A.Ş.")
        db.add(
            Opportunity(
                tenant_slug=t,
                company_id=c.id,
                name="D1",
                amount=100000,
                currency="TRY",
                campaign="Meta Ads",
            )
        )
        db.add(
            Opportunity(
                tenant_slug=t,
                company_id=c.id,
                name="D2",
                amount=300000,
                currency="TRY",
                campaign="Meta Ads",
            )
        )
        db.add(
            Opportunity(
                tenant_slug=t,
                company_id=c.id,
                name="D3",
                amount=50000,
                currency="TRY",
                campaign="Google Ads",
            )
        )
        db.commit()
        out = compute_campaign(db, t)
    assert out["attributed_revenue"] == 450000
    assert out["top_channel"] == "Meta Ads"
    assert out["currency"] == "₺"


def test_campaign_falls_back_to_total_pipeline_when_unattributed():
    t = "t_camp_unattr"
    with Session(get_engine()) as db:
        c = _seed_company(db, t, name="Pipeline A.Ş.")
        db.add(
            Opportunity(
                tenant_slug=t, company_id=c.id, name="P1", amount=70000, currency="USD"
            )
        )
        db.commit()
        out = compute_campaign(db, t)
    assert out["attributed_revenue"] == 70000
    assert out["currency"] == "$"
    assert out["top_channel"] == ""


# ── Buying signals ───────────────────────────────────────────────────────────
def test_buying_signals_fused_from_records():
    t = "t_sig_real"
    with Session(get_engine()) as db:
        hot = _seed_company(db, t, name="Sıcak A.Ş.", merged_count=3)
        warm = _seed_company(db, t, name="Ilık Ltd")
        db.add(Lead(tenant_slug=t, company_id=hot.id, score=0.9, intent="high"))
        db.add(
            Lead(
                tenant_slug=t,
                company_id=warm.id,
                score=0.5,
                intent="medium",
                status="engaged",
            )
        )
        db.add(
            Opportunity(
                tenant_slug=t,
                company_id=hot.id,
                name="Fresh",
                amount=120000,
                currency="TRY",
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        out = compute_buying_signals(db, t)
    icons = {s["icon"] for s in out["signals"]}
    assert "🔥" in icons  # high intent
    assert "📈" in icons  # engaged
    assert "🎯" in icons  # fresh opportunity
    assert "↻" in icons  # entity-resolution merge
    assert out["signal_types"] == len(icons)


def test_buying_signals_empty_when_no_records():
    with Session(get_engine()) as db:
        out = compute_buying_signals(db, "t_sig_empty")
    assert out == {"signals": [], "signal_types": 0}


# ── AEO (external probe → agent payload) ─────────────────────────────────────
def test_aeo_neutral_fallback_when_no_run():
    assert aeo_from_payload(None) == {
        "visibility_pct": None,
        "down_categories": 0,
        "categories_total": 8,
    }


def test_aeo_passthrough_from_payload():
    out = aeo_from_payload(
        {"visibility_pct": 41, "down_categories": 2, "categories_total": 8}
    )
    assert out["visibility_pct"] == 41
    assert out["down_categories"] == 2
