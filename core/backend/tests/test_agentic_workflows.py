# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Agentic workflow runner — agent chain + threaded context + approvals."""

from __future__ import annotations

import json

import pytest

from app.agentic_workflows import (
    list_runs,
    palette,
    run_workflow,
    run_workflow_graph,
)


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


def _full_pipeline_graph() -> dict:
    """trigger → agent → retrieval → policy → agent → consent → approval → action."""
    return {
        "name": "Full pipeline",
        "nodes": [
            {"id": "trg", "kind": "trigger", "name": "Inbound"},
            {"id": "tri", "kind": "agent", "name": "Triage", "agent_id": "inbound_triage"},
            {"id": "ret", "kind": "retrieval", "name": "RAG"},
            {"id": "pol", "kind": "policy", "name": "Policy"},
            {"id": "kno", "kind": "agent", "name": "Knowledge", "agent_id": "knowledge_base"},
            {"id": "con", "kind": "consent", "name": "Consent"},
            {"id": "apr", "kind": "approval", "name": "Approval"},
            {"id": "act", "kind": "action", "name": "Action"},
        ],
        "edges": [
            {"source": "trg", "target": "tri"}, {"source": "tri", "target": "ret"},
            {"source": "ret", "target": "pol"}, {"source": "pol", "target": "kno"},
            {"source": "kno", "target": "con"}, {"source": "con", "target": "apr"},
            {"source": "apr", "target": "act"},
        ],
    }


async def test_run_graph_executes_every_wired_node(_stub, monkeypatch) -> None:
    """Regression: the graph runner runs EVERY wired node (agent + retrieval +
    policy + consent + approval + action), not just the agent nodes — so the run
    mirrors the pipeline on the canvas (step_count 7, not 2)."""
    async def _no_hits(question, **kw):
        return []
    monkeypatch.setattr("app.rag.hybrid.query_hybrid", _no_hits)

    out = await run_workflow_graph(
        tenant_slug="tG", name="Full pipeline", graph=_full_pipeline_graph(),
        input_text="Fiyat nedir?", trigger="web form", actor="a@x.io",
    )
    assert out["status"] == "done"
    assert out["step_count"] == 7          # all 7 non-trigger wired nodes ran
    kinds = [r.get("kind") for r in out["results"]]
    assert kinds.count("agent") == 2
    for k in ("retrieval", "policy", "consent", "approval", "action"):
        assert k in kinds, f"{k} node was not executed"


async def test_run_graph_skips_unconnected_nodes(_stub, monkeypatch) -> None:
    """A node dropped on the canvas but never wired is not part of the flow."""
    async def _no_hits(question, **kw):
        return []
    monkeypatch.setattr("app.rag.hybrid.query_hybrid", _no_hits)
    graph = {
        "name": "wired+orphan",
        "nodes": [
            {"id": "trg", "kind": "trigger", "name": "T"},
            {"id": "a1", "kind": "agent", "name": "A1", "agent_id": "inbound_triage"},
            {"id": "orphan", "kind": "action", "name": "Orphan"},
        ],
        "edges": [{"source": "trg", "target": "a1"}],
    }
    out = await run_workflow_graph(
        tenant_slug="tO", name="x", graph=graph, input_text="hi", actor="a@x.io",
    )
    assert out["step_count"] == 1          # only the wired agent; orphan skipped
