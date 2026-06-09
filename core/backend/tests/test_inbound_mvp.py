# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Inbound Intelligence MVP — triage classifies + drafts + opens approval."""

from __future__ import annotations

import json

import pytest

from app.inbound import INTENTS, triage_inbound


@pytest.fixture
def _stub_runtime(monkeypatch):
    async def _no_rag(agent, task, **kw):
        return []

    async def _fake(agent, prompt, **kw):
        return json.dumps({
            "summary": "Pricing talebi sınıflandı",
            "recommended_action": "fiyat taslağı gönder",
            "confidence": 0.9,
            "payload": {"intent": "pricing_request", "draft": "Merhaba, fiyat..."},
        }), "groq"

    monkeypatch.setattr("app.agents.runtime._gather_evidence", _no_rag)
    monkeypatch.setattr("app.agents.runtime._complete", _fake)


async def test_triage_classifies_and_opens_approval(_stub_runtime) -> None:
    out = await triage_inbound(
        "Premium PVC fiyatı nedir?", tenant_slug="tI",
        channel="web", from_email="musteri@x.io", actor="admin@x.io",
    )
    assert out["intent"] == "pricing_request"
    assert out["intent"] in INTENTS
    assert out["draft"].startswith("Merhaba")
    assert out["requires_approval"] is True   # inbound_triage = medium risk
    assert out["run_id"] is not None
    # approval item opened with the inbound channel + sender
    assert out["approval"] is not None
    assert out["approval"]["channel"] == "web"
    assert out["approval"]["target_person"] == "musteri@x.io"
    assert out["approval"]["status"] == "pending"


async def test_unknown_intent_falls_back(monkeypatch) -> None:
    async def _no_rag(agent, task, **kw):
        return []

    async def _fake(agent, prompt, **kw):
        return json.dumps({"summary": "x", "confidence": 0.5,
                           "payload": {"intent": "made_up_intent"}}), "groq"

    monkeypatch.setattr("app.agents.runtime._gather_evidence", _no_rag)
    monkeypatch.setattr("app.agents.runtime._complete", _fake)

    out = await triage_inbound("merhaba", tenant_slug="tI2", actor="a@x.io")
    assert out["intent"] == "sales_inquiry"  # invalid → safe default
