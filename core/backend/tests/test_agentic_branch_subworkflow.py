# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Agentic engine — real branch routing + nested sub_workflow (roadmap F3).

branch: evaluate a condition over upstream outputs, then prune the downstream
of the edges that don't match (when="true"/"false"). sub_workflow: run a saved
workflow nested, depth-guarded so a cyclic reference terminates.
"""

from __future__ import annotations

from app.agentic_workflows import run_workflow_graph
from app.agentic_workflows import service as svc


def _result(out, kind):
    return next((r for r in out["results"] if r.get("kind") == kind), None)


def _by_name(out, name):
    return next((r for r in out["results"] if r.get("name") == name), None)


async def test_branch_prunes_the_untaken_path():
    """A branch with an empty condition (→ true) fires its when='true' edge and
    prunes the when='false' downstream."""
    graph = {
        "nodes": [
            {"id": "t", "kind": "trigger", "name": "Start"},
            {"id": "b", "kind": "branch", "name": "Gate", "config": {}},
            {"id": "yes", "kind": "action", "name": "YesPath"},
            {"id": "no", "kind": "action", "name": "NoPath"},
        ],
        "edges": [
            {"source": "t", "target": "b"},
            {"source": "b", "target": "yes", "when": "true"},
            {"source": "b", "target": "no", "when": "false"},
        ],
    }
    out = await run_workflow_graph(
        tenant_slug="tB", name="branch", graph=graph, input_text="go",
        trigger="manual", actor="a@x.io",
    )
    assert _result(out, "branch")["decision"] == "true"
    assert _by_name(out, "YesPath")["status"] == "executed"
    no = _by_name(out, "NoPath")
    assert no["status"] == "skipped" and no["note"] == "branch not taken"


async def test_branch_condition_false_prunes_true_path():
    graph = {
        "nodes": [
            {"id": "t", "kind": "trigger", "name": "Start"},
            {"id": "b", "kind": "branch", "name": "Gate",
             "config": {"condition_expr": "1 == 2"}},
            {"id": "yes", "kind": "action", "name": "YesPath"},
            {"id": "no", "kind": "action", "name": "NoPath"},
        ],
        "edges": [
            {"source": "t", "target": "b"},
            {"source": "b", "target": "yes", "when": "true"},
            {"source": "b", "target": "no", "when": "false"},
        ],
    }
    out = await run_workflow_graph(
        tenant_slug="tB", name="branch", graph=graph, input_text="go",
        trigger="manual", actor="a@x.io",
    )
    assert _result(out, "branch")["decision"] == "false"
    assert _by_name(out, "NoPath")["status"] == "executed"
    assert _by_name(out, "YesPath")["status"] == "skipped"


async def test_branch_merge_node_survives_when_reachable_via_taken_path():
    """A node downstream of BOTH branches must NOT be pruned (it's reachable via
    the taken path)."""
    graph = {
        "nodes": [
            {"id": "t", "kind": "trigger", "name": "Start"},
            {"id": "b", "kind": "branch", "name": "Gate", "config": {}},
            {"id": "yes", "kind": "action", "name": "YesPath"},
            {"id": "no", "kind": "action", "name": "NoPath"},
            {"id": "merge", "kind": "action", "name": "Merge"},
        ],
        "edges": [
            {"source": "t", "target": "b"},
            {"source": "b", "target": "yes", "when": "true"},
            {"source": "b", "target": "no", "when": "false"},
            {"source": "yes", "target": "merge"},
            {"source": "no", "target": "merge"},
        ],
    }
    out = await run_workflow_graph(
        tenant_slug="tB", name="merge", graph=graph, input_text="go",
        trigger="manual", actor="a@x.io",
    )
    assert _by_name(out, "Merge")["status"] == "executed"  # not pruned


async def test_sub_workflow_runs_nested_saved_workflow(monkeypatch):
    saved = {
        "name": "child",
        "nodes": [
            {"id": "ct", "kind": "trigger", "name": "ChildStart"},
            {"id": "ca", "kind": "action", "name": "ChildAction"},
        ],
        "edges": [{"source": "ct", "target": "ca"}],
    }
    monkeypatch.setattr(
        svc, "get_definition",
        lambda *, tenant_slug, key="default": {
            "key": key, "name": "child", "graph": saved, "saved": True,
        },
    )
    graph = {
        "nodes": [
            {"id": "t", "kind": "trigger", "name": "Start"},
            {"id": "sw", "kind": "sub_workflow", "name": "Child",
             "config": {"workflow_key": "child"}},
        ],
        "edges": [{"source": "t", "target": "sw"}],
    }
    out = await run_workflow_graph(
        tenant_slug="tS", name="parent", graph=graph, input_text="go",
        trigger="manual", actor="a@x.io",
    )
    sw = _result(out, "sub_workflow")
    assert sw["status"] == "done"
    assert sw["key"] == "child"
    assert sw["sub_steps"] >= 1  # the child's action ran


async def test_sub_workflow_unknown_key_is_skipped(monkeypatch):
    monkeypatch.setattr(
        svc, "get_definition",
        lambda *, tenant_slug, key="default": {
            "key": key, "name": key, "graph": {}, "saved": False,
        },
    )
    graph = {
        "nodes": [
            {"id": "t", "kind": "trigger", "name": "Start"},
            {"id": "sw", "kind": "sub_workflow", "name": "Missing",
             "config": {"workflow_key": "nope"}},
        ],
        "edges": [{"source": "t", "target": "sw"}],
    }
    out = await run_workflow_graph(
        tenant_slug="tS", name="parent", graph=graph, input_text="go",
        trigger="manual", actor="a@x.io",
    )
    sw = _result(out, "sub_workflow")
    assert sw["status"] == "skipped" and "not found" in sw["note"]
    assert out["status"] == "partial"


async def test_sub_workflow_depth_guard_terminates_self_reference(monkeypatch):
    """A workflow whose sub_workflow points back to itself must terminate via
    the depth guard, not recurse forever."""
    self_graph = {
        "name": "loopy",
        "nodes": [
            {"id": "t", "kind": "trigger", "name": "Start"},
            {"id": "sw", "kind": "sub_workflow", "name": "Self",
             "config": {"workflow_key": "loopy"}},
        ],
        "edges": [{"source": "t", "target": "sw"}],
    }
    monkeypatch.setattr(
        svc, "get_definition",
        lambda *, tenant_slug, key="default": {
            "key": key, "name": "loopy", "graph": self_graph, "saved": True,
        },
    )
    # must return (not hang / RecursionError)
    out = await run_workflow_graph(
        tenant_slug="tS", name="loopy", graph=self_graph, input_text="go",
        trigger="manual", actor="a@x.io",
    )
    assert out["status"] in ("partial", "done")
    # at the deepest level the sub_workflow is skipped on the depth guard
    assert any(
        r.get("kind") == "sub_workflow" and r.get("status") == "skipped"
        for r in out["results"]
    ) or out["status"] == "partial"
