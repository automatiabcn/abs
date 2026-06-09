# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Agentic workflow runner — agent chain + threaded context + approvals."""

from __future__ import annotations

import json

import pytest

from app.agentic_workflows import list_runs, palette, run_workflow


def test_palette_has_agents_and_kinds() -> None:
    p = palette()
    assert "agent" in p["node_kinds"] and "approval" in p["node_kinds"]
    total = sum(len(v) for v in p["agents"].values())
    assert total == 21


@pytest.fixture
def _stub(monkeypatch):
    async def _no_rag(agent, task, **kw):
        return []

    async def _fake(agent, prompt, **kw):
        return json.dumps({"summary": f"{agent.id} tamam", "confidence": 0.8,
                           "payload": {}}), "groq"

    monkeypatch.setattr("app.agents.runtime._gather_evidence", _no_rag)
    monkeypatch.setattr("app.agents.runtime._complete", _fake)


async def test_run_chain_opens_approval(_stub) -> None:
    out = await run_workflow(
        tenant_slug="tW", name="Inbound→Cevap",
        steps=["inbound_triage", "knowledge_base"], input_text="Fiyat nedir?",
        trigger="manual", actor="a@x.io",
    )
    assert out["status"] == "done"
    assert out["step_count"] == 2
    assert out["steps_run"] == 2
    # inbound_triage is medium-risk → an approval is opened
    assert out["approvals_opened"] >= 1
    # second step saw threaded context (no error)
    assert all("summary" in r for r in out["results"])

    runs = list_runs(tenant_slug="tW")
    assert runs["total"] >= 1
    assert runs["runs"][0]["id"] == out["id"]
    # tenant isolation
    assert list_runs(tenant_slug="tW-empty")["total"] == 0


async def test_unknown_agent_step_is_partial(_stub) -> None:
    out = await run_workflow(
        tenant_slug="tW2", name="x", steps=["knowledge_base", "no_such_agent"],
        input_text="soru", actor="a@x.io",
    )
    assert out["status"] == "partial"
    assert any(r.get("skipped") == "unknown_agent" for r in out["results"])
