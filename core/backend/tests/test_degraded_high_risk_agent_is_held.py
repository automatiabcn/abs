"""Issue #136 — a degraded high-risk agent is held, not silently ungated.

`requires_approval=agent.requires_approval and not degraded` meant: no
provider → no approval item → the run returned as if answered. Decision
(2026-08-28): option (b) — refuse outright with the reason. The result says
"Held", proposes nothing, recommends "hold", and still carries no approval
(there is nothing to approve).
"""

from __future__ import annotations

import pytest

from app.agents import runtime


@pytest.mark.asyncio
async def test_no_provider_holds_a_high_risk_agent(monkeypatch):
    async def _no_answer(agent, prompt, **kw):
        return "", ""

    monkeypatch.setattr(runtime, "_complete", _no_answer)

    async def _no_evidence(*a, **kw):
        return []

    monkeypatch.setattr(runtime, "_gather_evidence", _no_evidence)
    r = await runtime.run_agent("outbound_draft", "draft the renewal email", tenant_id="t_held_1")
    assert r.risk == "high"
    assert r.degraded is True
    assert r.held is True
    assert r.requires_approval is False
    assert r.recommended_action == "hold"
    assert r.summary.startswith("Held —")
    assert "No provider answered" in r.summary
    assert r.to_dict()["held"] is True


@pytest.mark.asyncio
async def test_a_real_answer_is_not_held(monkeypatch):
    async def _answer(agent, prompt, **kw):
        return '{"summary":"Draft ready","confidence":0.8,"recommended_action":"send","payload":{"to":"x@y"}}', "groq"

    monkeypatch.setattr(runtime, "_complete", _answer)

    async def _no_evidence(*a, **kw):
        return []

    monkeypatch.setattr(runtime, "_gather_evidence", _no_evidence)
    r = await runtime.run_agent("outbound_draft", "draft the renewal email", tenant_id="t_held_2")
    assert r.held is False
    assert r.degraded is False
    assert r.requires_approval is True
