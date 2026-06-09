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

from app.db.growth_models import Company, Contact, ConnectorState, Lead, Opportunity, WorkflowRun
from app.db.models import AgentRun, ApprovalItem
from app.db.session import get_engine

logger = logging.getLogger(__name__)

_SENTINEL = "Demirel Yapı A.Ş."


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Company, sector, lead score/intent/consent, recommended_action, score breakdown.
_COMPANIES = [
    {
        "name": "Demirel Yapı A.Ş.", "sector": "İnşaat", "score": 0.87, "intent": "high",
        "consent": "izinli", "vkn": "1234567890", "domain": "demirelyapi.com.tr",
        "evidence": ["Pricing-page 3x ziyaret", "İş ilanı +4 (satınalma)", "ERP'de tekrar sipariş"],
        "merged_count": 3, "match_confidence": 0.96, "lifecycle": "customer",
        "opportunities": [
            {"name": "Q2 PVC projesi", "stage": "proposal", "amount": 420000, "campaign": "Meta Ads · Q2"},
            {"name": "Geçmiş teklif", "stage": "closed_won", "amount": 180000, "campaign": ""},
        ],
        "score_criteria": {
            "ICP uyumu": 0.92, "Satın alma ihtimali": 0.84, "Bütçe potansiyeli": 0.78,
            "Intent sinyali": 0.90, "Hizmet ihtiyacı": 0.81, "CRM geçmişi": 0.70,
            "ERP geçmişi (tekrar satın)": 0.88, "Zamanlama uygunluğu": 0.86,
            "İletişim izni": 1.0, "Veri güven skoru": 0.96,
        },
        "lead_evidence": [
            {"kind": "rag", "ref": "Geçmiş benzer müşteri teklifi · proposal-archive"},
            {"kind": "graph", "ref": "Account→2 Opportunity · geçmiş ₺420K fatura (ERP)"},
            {"kind": "signal", "ref": "Pricing-page ziyareti + iş ilanı artışı (+4)"},
        ],
        "buying_group": [
            {"name": "M. Demirel", "role": "decision_maker"},
            {"name": "Finans Yetkilisi", "role": "finance_approver"},
            {"name": "Teknik Değerlendirici 1", "role": "technical_evaluator"},
            {"name": "Asistan", "role": "gatekeeper"},
        ],
    },
    {
        "name": "Kaya İnşaat", "sector": "İnşaat", "score": 0.64, "intent": "medium",
        "consent": "izinli", "vkn": "2345678901", "domain": "kayainsaat.com",
        "evidence": ["Pricing-page ziyareti", "LinkedIn etkileşim"],
    },
    {
        "name": "Tekno Mühendislik", "sector": "Üretim", "score": 0.58, "intent": "medium",
        "consent": "kısmi", "vkn": "3456789012", "domain": "teknomuh.com",
        "evidence": ["Demo formu #2841", "Web crawl: yeni ürün hattı"],
    },
    {
        "name": "Mavi Lojistik", "sector": "Lojistik", "score": 0.31, "intent": "watching",
        "consent": "yok", "vkn": "4567890123", "domain": "mavilojistik.com",
        "evidence": ["Yeni lokasyon açılışı"],
    },
    {
        "name": "Tekno A.Ş.", "sector": "Üretim", "score": 0.52, "intent": "medium",
        "consent": "izinli", "vkn": "5678901234", "domain": "tekno.com.tr",
        "evidence": ["İş ilanı artışı +4", "Sektör raporu eşleşmesi"],
    },
]

# Activity feed — (agent_id, summary, risk, requires_approval, minutes_ago, confidence, payload).
# `payload` carries the structured result the dashboard summary widgets read
# (latest run per agent), so AEO / campaign / CRM / signals are data-derived
# rather than hardcoded in the dashboard service.
_RUNS = [
    ("lead_discovery", "İstanbul bölgesinde 12 yeni ICP-uyumlu firma buldu · enrichment kuyruğuna alındı", "low", False, 2, 0.0, {}),
    ("lead_scoring", '"Demirel Yapı A.Ş." skorladı → 0.87 (yüksek) · 14 kanıt · top-3 RAG kaynak iliştirildi', "medium", False, 5, 0.87, {}),
    ("inbound_triage", 'Gelen talebi sınıfladı → "pricing_request" · cevap taslağı + CRM notu üretildi', "medium", True, 8, 0.79, {"intent": "pricing_request"}),
    ("competitive_intel", "Rakip fiyat değişikliği yakaladı · Battlecard Agent tetiklendi", "low", False, 14, 0.0, {}),
    ("aeo_visibility", "AI-cevaplarında 2 kategoride görünürlük düşüşü tespit etti · içerik-boşluk raporu üretildi", "low", False, 22, 0.0,
     {"visibility_pct": 41, "down_categories": 2, "categories_total": 8, "recommended": 3}),
    ("buying_signal", "16 sinyal türü tarandı · 5 yeni buying-signal füzyonlandı", "low", False, 28, 0.0,
     {"signals": [
         {"icon": "🔥", "label": "Pricing-page ziyareti", "company": "Kaya İnşaat"},
         {"icon": "📈", "label": "İş ilanı artışı +4", "company": "Tekno A.Ş."},
         {"icon": "🎯", "label": "Demo talebi", "company": "Form #2841"},
         {"icon": "🏢", "label": "Yeni lokasyon", "company": "Mavi Lojistik"},
         {"icon": "↻", "label": "Tekrar satın alma", "company": "ERP · 3 müşteri"},
     ], "signal_types": 16}),
    ("campaign_attribution", "Q2 kampanya → gelir eşlemesi · Meta Ads en yüksek dönüşüm · ERP-doğrulamalı", "medium", False, 35, 0.0,
     {"attributed_revenue": 1240000, "currency": "₺", "top_channel": "Meta Ads", "period": "Q2"}),
    ("crm_hygiene", "CRM tarandı · 11 düzeltme önerisi (duplicate + eksik alan)", "medium", False, 45, 0.0,
     {"health_pct": 86, "fix_suggestions": 11}),
]

# Pending approvals. The first two are detailed cards; the rest populate the
# "Kuyruk (5 daha)" queue table. `evidence` items are {kind, ref} so the card
# can split KANIT·RAG / KANIT·GRAPH / CONSENT / POLICY like the mockup.
_APPROVALS = [
    {
        "agent_id": "inbound_triage", "risk": "medium", "consent": "izinli",
        "policy": "requires_approval", "company": "Demirel Yapı A.Ş.", "channel": "email", "mins": 8,
        "action": '"Demirel Yapı A.Ş." pricing talebine kaynak-gösteren cevap taslağı → email gönderimi + CRM notu',
        "rationale": 'Gelen talep "pricing_request" sınıflandı (0.94 güven). Müşteri ICP-uyumlu, daha önce 2 kez teklif aldı. Standart fiyat politikası + benzer müşteri teklif geçmişi kullanıldı.',
        "message": "Merhaba, talebiniz için teşekkürler. Premium PVC seriniz için fiyat aralığımız [1] ve uygulama süreci [2] ektedir. Önceki projenize benzer bir çözüm önerebiliriz…",
        "evidence": [
            {"kind": "rag", "ref": "[1] fiyat-politikasi.pdf"},
            {"kind": "rag", "ref": "[2] uygulama-sureci.docx"},
            {"kind": "graph", "ref": "Account→2 Opportunity geçmiş teklif"},
        ],
    },
    {
        "agent_id": "outbound_draft", "risk": "high", "consent": "opt-in (İYS)",
        "policy": "requires approval + audit", "company": "Kaya İnşaat", "channel": "email", "mins": 21,
        "action": '"Kaya İnşaat" karar-vericisine outbound email (buying-signal: pricing-page ziyareti)',
        "rationale": "Lead skoru 0.81. Pricing-page ziyareti + iş ilanı artışı sinyali. Consent İYS'de doğrulandı, opt-in kaynağı: web formu. Domain reputation sağlıklı, bounce %0.4.",
        "message": "Merhaba, inşaat projeleriniz için PVC çözümlerimizi 2 dakikada özetleyebilir miyim?",
        "evidence": [
            {"kind": "consent", "ref": "email izni · 2026-03 İYS kayıtlı"},
            {"kind": "policy", "ref": "requires approval + audit"},
        ],
    },
    # ── Kuyruk (5 daha) ──
    {"agent_id": "crm_hygiene", "risk": "medium", "consent": "", "policy": "approval",
     "company": "", "channel": "", "mins": 30, "action": "11 duplicate birleştir", "rationale": "", "message": "", "evidence": []},
    {"agent_id": "campaign_attribution", "risk": "medium", "consent": "", "policy": "approval",
     "company": "", "channel": "", "mins": 40, "action": "CRM opportunity alan-güncelle", "rationale": "", "message": "", "evidence": []},
    {"agent_id": "social_strategy", "risk": "medium", "consent": "", "policy": "approval",
     "company": "", "channel": "", "mins": 52, "action": "reklam audience önerisi", "rationale": "", "message": "", "evidence": []},
    {"agent_id": "voice_call", "risk": "high", "consent": "kısmi", "policy": "consent check",
     "company": "", "channel": "voice", "mins": 64, "action": "outbound arama önerisi (10 lead)", "rationale": "", "message": "", "evidence": []},
    {"agent_id": "outbound_draft", "risk": "high", "consent": "opt-in", "policy": "approval+audit",
     "company": "", "channel": "whatsapp", "mins": 75, "action": "WhatsApp şablon mesajı", "rationale": "", "message": "", "evidence": []},
]

_CONNECTORS = ["parasut", "hubspot", "gmail"]

# Workflow run history — (name, trigger, step_count, status, approvals, elapsed_ms, mins_ago).
_WORKFLOW_RUNS = [
    ("Inbound → Cevap Taslağı", "web form", 7, "done", 1, 4200, 12),
    ("Inbound → Cevap Taslağı", "email", 7, "partial", 1, 2100, 34),
    ("Inbound → Cevap Taslağı", "WhatsApp", 7, "done", 0, 5000, 58),
]


def _already_seeded(db: Session, tenant: str) -> bool:
    return db.exec(
        select(Company).where(Company.tenant_slug == tenant, Company.name == _SENTINEL)
    ).first() is not None


def seed_growth_demo(tenant_slug: str = "default", *, force: bool = False) -> dict:
    """Idempotently insert the demo growth dataset. Returns a small summary."""
    tenant = (tenant_slug or "default").strip() or "default"
    now = _now()
    created = {"companies": 0, "leads": 0, "runs": 0, "approvals": 0, "connectors": 0, "contacts": 0}

    with Session(get_engine()) as db:
        if not force and _already_seeded(db, tenant):
            return {"ok": True, "skipped": "already_seeded", **created}

        run_id_by_agent: dict[str, int] = {}

        # Companies + leads + a primary contact each.
        for c in _COMPANIES:
            company = Company(
                tenant_slug=tenant, name=c["name"], sector=c["sector"],
                vkn=c.get("vkn", ""), domain=c.get("domain", ""),
                score=c["score"], lifecycle=c.get("lifecycle", "lead"),
                merged_count=c.get("merged_count", 1),
                match_confidence=c.get("match_confidence", 0.93),
                source="erp+crm+web",
            )
            db.add(company)
            db.commit()
            db.refresh(company)
            created["companies"] += 1

            for op in c.get("opportunities", []):
                db.add(Opportunity(
                    tenant_slug=tenant, company_id=company.id, name=op["name"],
                    stage=op["stage"], amount=op["amount"], currency="TRY",
                    campaign=op.get("campaign", ""),
                ))
            db.commit()

            # Buying group: a rich set for the flagship lead, else one contact.
            bg = c.get("buying_group") or [{"name": f"{c['name'].split()[0]} Yetkili", "role": "purchasing"}]
            for member in bg:
                db.add(Contact(
                    tenant_slug=tenant, company_id=company.id, name=member["name"],
                    email=f"{member['role']}@{c.get('domain', 'example.com')}",
                    role=member["role"], consent_status=c["consent"],
                ))
                created["contacts"] += 1

            score_json = json.dumps(
                c.get("score_criteria") or {"icp_fit": c["score"], "buying_signal": c["score"]},
                ensure_ascii=False,
            )
            evidence_json = json.dumps(
                c.get("lead_evidence") or c["evidence"], ensure_ascii=False
            )
            lead = Lead(
                tenant_slug=tenant, company_id=company.id, source="erp+crm+web",
                intent=c["intent"], score=c["score"], status="scored",
                consent_status=c["consent"], score_json=score_json, evidence_json=evidence_json,
            )
            db.add(lead)
            created["leads"] += 1
        db.commit()

        # Activity feed (agent_runs) — staggered timestamps.
        for agent_id, summary, risk, needs_approval, mins, conf, payload in _RUNS:
            run = AgentRun(
                tenant_slug=tenant, agent_id=agent_id, task="(demo seed)",
                summary=summary, confidence=conf, risk=risk,
                requires_approval=needs_approval, provider="gpt-oss-120b",
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
            db.add(ApprovalItem(
                tenant_slug=tenant, agent_id=ap["agent_id"],
                agent_run_id=run_id_by_agent.get(ap["agent_id"]),
                action=ap["action"], target_company=ap["company"], channel=ap["channel"],
                rationale=ap["rationale"], risk=ap["risk"], consent_status=ap["consent"],
                proposed_message=ap["message"],
                evidence_json=json.dumps(ap["evidence"], ensure_ascii=False),
                policy_result=ap["policy"], status="pending",
                created_at=now - timedelta(minutes=ap["mins"]),
            ))
            created["approvals"] += 1
        db.commit()

        # Workflow run history.
        for name, trigger, sc, st, ap, ms, mins in _WORKFLOW_RUNS:
            db.add(WorkflowRun(
                tenant_slug=tenant, name=name, trigger=trigger,
                steps_json=json.dumps(["inbound_triage", "knowledge_base"]),
                status=st, step_count=sc, approvals_opened=ap, elapsed_ms=ms,
                created_at=now - timedelta(minutes=mins),
            ))
        db.commit()

        # Connector states.
        for cid in _CONNECTORS:
            existing = db.exec(
                select(ConnectorState).where(
                    ConnectorState.tenant_slug == tenant, ConnectorState.connector_id == cid
                )
            ).first()
            if not existing:
                db.add(ConnectorState(
                    tenant_slug=tenant, connector_id=cid, status="connected",
                    health=100 if cid != "gmail" else 82,
                    connected_at=now - timedelta(days=3), last_sync_at=now - timedelta(minutes=12),
                ))
                created["connectors"] += 1
        db.commit()

    logger.info("growth demo seeded tenant=%s %s", tenant, created)
    return {"ok": True, **created}
