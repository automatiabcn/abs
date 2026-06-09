# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Lead Intelligence — create company+lead, score via agent, priority list."""

from __future__ import annotations

import json

import pytest

from app.leads import service


def test_create_and_list_priority() -> None:
    cid = service.create_company(tenant_slug="tL", name="Demirel Yapı A.Ş.", sector="İnşaat")
    lead = service.create_lead(tenant_slug="tL", company_id=cid, source="web", owner="a@x.io")
    assert lead["company_name"] == "Demirel Yapı A.Ş."
    assert lead["status"] == "new"
    listed = service.list_leads(tenant_slug="tL")
    assert listed["total"] >= 1
    # tenant isolation
    assert service.list_leads(tenant_slug="tL-empty-xyz")["total"] == 0
    assert service.get_lead(tenant_slug="tOther", lead_id=lead["id"]) is None


async def test_score_lead_persists(monkeypatch) -> None:
    async def _no_rag(agent, task, **kw):
        return []

    async def _fake(agent, prompt, **kw):
        return json.dumps({
            "summary": "yüksek skor",
            "confidence": 0.6,
            "payload": {"score": 0.87, "criteria": {"icp": 0.92, "intent": 0.9}},
        }), "groq"

    monkeypatch.setattr("app.agents.runtime._gather_evidence", _no_rag)
    monkeypatch.setattr("app.agents.runtime._complete", _fake)

    cid = service.create_company(tenant_slug="tS", name="Kaya İnşaat", sector="İnşaat")
    lead = service.create_lead(tenant_slug="tS", company_id=cid, source="crm")
    scored = await service.score_lead(tenant_slug="tS", lead_id=lead["id"], actor="a@x.io")

    assert scored is not None
    assert scored["score"] == 0.87           # payload.score wins over confidence
    assert scored["intent"] == "high"        # >= 0.8
    assert scored["status"] == "scored"
    assert scored["score_breakdown"]["icp"] == 0.92
    # priority list now ordered by score
    top = service.list_leads(tenant_slug="tS")["items"][0]
    assert top["id"] == lead["id"]


async def test_score_unknown_lead_returns_none() -> None:
    assert await service.score_lead(tenant_slug="tS", lead_id=999999) is None
