# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Stage D — Workflow Designer graph definition + topological run order."""

from __future__ import annotations

import pytest
from sqlmodel import Session, func, select

from app.agentic_workflows import (
    get_definition,
    ordered_agent_steps,
    run_workflow,
    save_definition,
)
from app.agents.registry import AGENTS
from app.db.growth_models import WorkflowRun
from app.db.session import get_engine


def _known_agents(n: int) -> list[str]:
    return list(AGENTS.keys())[:n]


# ── ordered_agent_steps (topological) ────────────────────────────────────────
def test_ordered_steps_follows_edges():
    a, b = _known_agents(2)
    graph = {
        "nodes": [
            {"id": "t", "kind": "trigger"},
            {"id": "n2", "kind": "agent", "agent_id": b},
            {"id": "n1", "kind": "agent", "agent_id": a},
        ],
        # edges force n1 before n2 even though n2 is listed first
        "edges": [{"source": "t", "target": "n1"}, {"source": "n1", "target": "n2"}],
    }
    assert ordered_agent_steps(graph) == [a, b]


def test_ordered_steps_skips_unknown_agent_ids():
    a = _known_agents(1)[0]
    graph = {
        "nodes": [
            {"id": "n1", "kind": "agent", "agent_id": a},
            {"id": "n2", "kind": "agent", "agent_id": "does_not_exist"},
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    assert ordered_agent_steps(graph) == [a]


def test_ordered_steps_ignores_non_agent_nodes():
    a = _known_agents(1)[0]
    graph = {
        "nodes": [
            {"id": "t", "kind": "trigger"},
            {"id": "a1", "kind": "agent", "agent_id": a},
            {"id": "act", "kind": "action"},
        ],
        "edges": [{"source": "t", "target": "a1"}, {"source": "a1", "target": "act"}],
    }
    assert ordered_agent_steps(graph) == [a]


def test_ordered_steps_handles_cycle_without_hanging():
    a, b = _known_agents(2)
    graph = {
        "nodes": [
            {"id": "n1", "kind": "agent", "agent_id": a},
            {"id": "n2", "kind": "agent", "agent_id": b},
        ],
        "edges": [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n1"}],
    }
    # cyclic → falls back to insertion order, still returns both
    assert set(ordered_agent_steps(graph)) == {a, b}


def test_ordered_steps_empty_graph():
    assert ordered_agent_steps({"nodes": [], "edges": []}) == []


def test_ordered_steps_ignores_dangling_edges():
    # an edge pointing at a deleted/non-existent node must not crash or run it
    a = _known_agents(1)[0]
    graph = {
        "nodes": [
            {"id": "t", "kind": "trigger"},
            {"id": "a1", "kind": "agent", "agent_id": a},
        ],
        "edges": [
            {"source": "t", "target": "a1"},
            {"source": "a1", "target": "ghost"},  # 'ghost' was deleted
            {"source": "missing", "target": "a1"},
        ],
    }
    assert ordered_agent_steps(graph) == [a]


def test_ordered_steps_skips_unwired_agent():
    a, b = _known_agents(2)
    graph = {
        "nodes": [
            {"id": "t", "kind": "trigger"},
            {"id": "wired", "kind": "agent", "agent_id": a},
            {"id": "orphan", "kind": "agent", "agent_id": b},  # no edges
        ],
        "edges": [{"source": "t", "target": "wired"}],
    }
    # the unwired 'orphan' must not run; only the connected agent does
    assert ordered_agent_steps(graph) == [a]


# ── get / save definition ────────────────────────────────────────────────────
def test_get_definition_returns_default_when_unsaved():
    out = get_definition(tenant_slug="t_wf_default", key="default")
    assert out["saved"] is False
    assert len(out["graph"]["nodes"]) == 8
    assert out["ordered_steps"] == ["inbound_triage", "knowledge_base"]


def test_save_then_get_roundtrips_positions_and_edges():
    a = _known_agents(1)[0]
    graph = {
        "name": "Test Akış",
        "nodes": [
            {
                "id": "t",
                "kind": "trigger",
                "name": "T",
                "desc": "",
                "x": 10,
                "y": 20,
                "agent_id": None,
            },
            {
                "id": "a1",
                "kind": "agent",
                "name": "A",
                "desc": "",
                "x": 200,
                "y": 40,
                "agent_id": a,
            },
        ],
        "edges": [{"source": "t", "target": "a1"}],
    }
    saved = save_definition(
        tenant_slug="t_wf_rt", key="default", name="Test Akış", graph=graph
    )
    assert saved["saved"] is True
    assert saved["node_count"] == 2
    assert saved["edge_count"] == 1
    assert saved["ordered_steps"] == [a]

    out = get_definition(tenant_slug="t_wf_rt", key="default")
    assert out["saved"] is True
    assert out["graph"]["name"] == "Test Akış"
    node = next(n for n in out["graph"]["nodes"] if n["id"] == "a1")
    assert node["x"] == 200 and node["y"] == 40


@pytest.mark.asyncio
async def test_dry_run_persists_nothing():
    t = "t_wf_dry"
    a = list(AGENTS.keys())[0]

    def _count():
        with Session(get_engine()) as db:
            return db.exec(
                select(func.count())
                .select_from(WorkflowRun)
                .where(WorkflowRun.tenant_slug == t)
            ).one()

    before = _count()
    out = await run_workflow(
        tenant_slug=t, name="Preview", steps=[a], input_text="merhaba", dry_run=True
    )
    assert out["dry_run"] is True
    assert out["id"] is None
    assert out["approvals_opened"] == 0
    assert "would_open_approvals" in out
    assert _count() == before  # no run row persisted


def test_save_is_tenant_isolated():
    save_definition(
        tenant_slug="t_wf_iso_a",
        key="default",
        name="A graph",
        graph={"nodes": [{"id": "x", "kind": "trigger"}], "edges": []},
    )
    other = get_definition(tenant_slug="t_wf_iso_b", key="default")
    assert other["saved"] is False  # B never saved → still default
