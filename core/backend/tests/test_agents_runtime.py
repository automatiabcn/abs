# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Agent Registry + Runtime — unit tests (SQLite lane, no live providers).

The model call (``_complete``) and RAG context (``_gather_evidence``) are
stubbed so the test asserts the runtime's structure: scoped prompt → structured
parse → confidence clamp → risk/approval routing → graceful degrade.
"""

from __future__ import annotations

import json

import pytest

from app.agents import registry
from app.agents.runtime import run_agent


def test_registry_shape() -> None:
    assert len(registry.AGENTS) == 21
    # every agent has a category the UI knows how to group
    for a in registry.AGENTS.values():
        assert a.category in registry.CATEGORY_LABELS
        assert a.risk in (registry.RISK_LOW, registry.RISK_MEDIUM, registry.RISK_HIGH)
    grouped = registry.agents_by_category()
    assert sum(len(v) for v in grouped.values()) == 21


def test_get_agent_known_and_unknown() -> None:
    assert registry.get_agent("knowledge_base").name == "Knowledge Base Agent"
    assert registry.get_agent("nope") is None


def test_risk_drives_approval() -> None:
    assert registry.get_agent("knowledge_base").requires_approval is False  # low
    assert registry.get_agent("inbound_triage").requires_approval is True  # medium
    assert registry.get_agent("outbound_draft").requires_approval is True  # high


@pytest.fixture
def _no_rag(monkeypatch):
    async def _empty(agent, task, **kw):
        return []

    monkeypatch.setattr("app.agents.runtime._gather_evidence", _empty)


async def test_run_agent_structured(monkeypatch, _no_rag) -> None:
    async def _fake(agent, prompt, **kw):
        return json.dumps(
            {
                "summary": "İki kategoride görünürlük düşüşü",
                "recommended_action": "FAQ içeriği ekle",
                "confidence": 0.82,
                "payload": {"categories": ["pvc", "kapı"]},
            }
        ), "groq"

    monkeypatch.setattr("app.agents.runtime._complete", _fake)

    res = await run_agent(
        "aeo_visibility", "AI görünürlüğünü analiz et", tenant_id="t1"
    )
    assert res.agent_id == "aeo_visibility"
    assert res.output_kind == "aeo_report"
    assert res.summary.startswith("İki kategoride")
    assert res.confidence == 0.82
    assert res.payload == {"categories": ["pvc", "kapı"]}
    assert res.requires_approval is False
    assert res.provider == "groq"


async def test_run_agent_degrades_without_provider(monkeypatch, _no_rag) -> None:
    async def _none(agent, prompt, **kw):
        return "", ""

    monkeypatch.setattr("app.agents.runtime._complete", _none)

    res = await run_agent("knowledge_base", "what does it cost?", tenant_id="t1")
    # Degraded but structured: it never raises, the confidence is floored, and
    # the summary says plainly that nothing usable came back — a degraded run
    # must not be mistaken for a real proposal.
    assert res.confidence == 0.0
    assert "no usable answer" in res.summary
    assert res.requires_approval is False


async def test_run_engagement_agent_flags_approval(monkeypatch, _no_rag) -> None:
    async def _fake(agent, prompt, **kw):
        return json.dumps({"summary": "taslak", "confidence": 0.7}), "cloudflare"

    monkeypatch.setattr("app.agents.runtime._complete", _fake)

    res = await run_agent("outbound_draft", "taslak yaz", tenant_id="t1")
    assert res.risk == registry.RISK_HIGH
    assert res.requires_approval is True


async def test_run_unknown_agent_raises() -> None:
    with pytest.raises(KeyError):
        await run_agent("does_not_exist", "x", tenant_id="t1")


async def test_confidence_clamped(monkeypatch, _no_rag) -> None:
    async def _fake(agent, prompt, **kw):
        return json.dumps({"summary": "x", "confidence": 9.9}), "groq"

    monkeypatch.setattr("app.agents.runtime._complete", _fake)
    res = await run_agent("lead_scoring", "skorla", tenant_id="t1")
    assert res.confidence == 1.0


async def test_degraded_engagement_agent_opens_no_approval(
    monkeypatch, _no_rag
) -> None:
    # No provider → degraded → even a high-risk agent must NOT gate an approval.
    async def _none(agent, prompt, **kw):
        return "", ""

    monkeypatch.setattr("app.agents.runtime._complete", _none)
    res = await run_agent("outbound_draft", "taslak", tenant_id="t1")
    assert res.degraded is True
    assert res.requires_approval is False


async def test_complete_reads_provider_response_text_field(
    monkeypatch, _no_rag
) -> None:
    """Regression: the runtime must read ProviderResponse.text (not .completion).
    Reading the wrong field made every agent degrade even with a live provider.
    Stubs the cascade (NOT _complete) so the real field extraction runs."""
    from app.providers.schemas import ProviderResponse

    async def _fake_cascade(prompt, **kw):
        return ProviderResponse(
            text='{"summary": "gerçek cevap", "confidence": 0.7, "payload": {}}',
            provider="groq",
        )

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _fake_cascade)
    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers", lambda **k: ["groq"]
    )

    res = await run_agent("knowledge_base", "soru", tenant_id="default")
    assert res.degraded is False
    assert res.summary == "gerçek cevap"
    assert res.confidence == 0.7
    assert res.provider == "groq"
