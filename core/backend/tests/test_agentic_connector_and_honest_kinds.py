# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Agentic Designer node-adding follow-up.

- A `connector` node now really runs the connector's adapter sync (was a silent
  structural "done" checkpoint that did nothing).
- `branch` / `sub_workflow` / unknown kinds — which the palette lets a user add
  but the engine cannot run — no longer report a false green; they are flagged
  `skipped` and the overall run becomes `partial`.
"""

from __future__ import annotations

import pytest

from app.agentic_workflows import run_workflow_graph


async def test_connector_node_runs_real_sync(monkeypatch):
    calls = {}

    async def _fake_sync(*, tenant_slug, connector_id, credentials_override=None):
        calls["tenant"] = tenant_slug
        calls["connector_id"] = connector_id
        return {"ok": True, "total": 42}

    monkeypatch.setattr("app.connectors.service.sync", _fake_sync)

    graph = {
        "nodes": [
            {"id": "trg", "kind": "trigger", "name": "Start"},
            {
                "id": "cx",
                "kind": "connector",
                "name": "HubSpot",
                "config": {"connector_id": "hubspot"},
            },
        ],
        "edges": [{"source": "trg", "target": "cx"}],
    }
    out = await run_workflow_graph(
        tenant_slug="tC",
        name="Connector run",
        graph=graph,
        input_text="",
        trigger="manual",
        actor="a@x.io",
    )
    assert calls == {"tenant": "tC", "connector_id": "hubspot"}
    cx = next(r for r in out["results"] if r.get("kind") == "connector")
    assert cx["status"] == "done"
    assert cx["synced"] == 42
    assert out["status"] == "done"


async def test_connector_node_dry_run_does_not_sync(monkeypatch):
    async def _boom(*a, **k):
        raise AssertionError("sync must not fire in dry-run")

    monkeypatch.setattr("app.connectors.service.sync", _boom)
    graph = {
        "nodes": [
            {"id": "trg", "kind": "trigger", "name": "Start"},
            {
                "id": "cx",
                "kind": "connector",
                "name": "HubSpot",
                "config": {"connector_id": "hubspot"},
            },
        ],
        "edges": [{"source": "trg", "target": "cx"}],
    }
    out = await run_workflow_graph(
        tenant_slug="tC",
        name="Preview",
        graph=graph,
        input_text="",
        trigger="manual",
        actor="a@x.io",
        dry_run=True,
    )
    cx = next(r for r in out["results"] if r.get("kind") == "connector")
    assert cx["status"] == "preview"


async def test_connector_without_id_is_skipped_and_partial():
    graph = {
        "nodes": [
            {"id": "trg", "kind": "trigger", "name": "Start"},
            {"id": "cx", "kind": "connector", "name": "Unconfigured"},
        ],
        "edges": [{"source": "trg", "target": "cx"}],
    }
    out = await run_workflow_graph(
        tenant_slug="tC",
        name="No id",
        graph=graph,
        input_text="",
        trigger="manual",
        actor="a@x.io",
    )
    cx = next(r for r in out["results"] if r.get("kind") == "connector")
    assert cx["status"] == "skipped"
    assert out["status"] == "partial"


# branch + sub_workflow are now really executed (see test_agentic_branch_subworkflow);
# only a genuinely-unknown kind should hit the honest catch-all.
@pytest.mark.parametrize("kind", ["frobnicate", "teleport"])
async def test_unimplemented_kind_is_honest_not_false_green(kind):
    graph = {
        "nodes": [
            {"id": "trg", "kind": "trigger", "name": "Start"},
            {"id": "x", "kind": kind, "name": kind},
        ],
        "edges": [{"source": "trg", "target": "x"}],
    }
    out = await run_workflow_graph(
        tenant_slug="tX",
        name="Honest",
        graph=graph,
        input_text="",
        trigger="manual",
        actor="a@x.io",
    )
    node = next(r for r in out["results"] if r.get("kind") == kind)
    assert node["status"] == "skipped"
    assert "not executed" in node["note"]
    assert out["status"] == "partial"
