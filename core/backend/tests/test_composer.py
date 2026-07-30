# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Composer runtime — a proposal is graded, blast-annotated, and risk-derived."""

from __future__ import annotations

import asyncio

import pytest

from app.codegraph import graph as codegraph
from app.composer import runtime as composer


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    # Isolate both the code-graph and (unused here) data dirs.
    monkeypatch.setattr(codegraph.settings, "data_dir", str(tmp_path / "data"))
    ws = tmp_path / "ws"
    ws.mkdir()
    # a() -> helper(); changing helper should blast-radius onto a().
    (ws / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (ws / "app.py").write_text("def a():\n    return helper()\n", encoding="utf-8")
    codegraph.build(str(ws), key="wtest")
    return ws


def _stub_generation(monkeypatch, parsed, tried=("groq",), meta=None):
    async def _fake(task, *, tenant_id, project_slug, user_subject):
        return parsed, list(tried), dict(meta or {})

    monkeypatch.setattr(composer, "_generate_edits", _fake)


def _stub_judge(monkeypatch, score=8.0):
    async def _fake_judge(diff, path=None):
        return {"combined_score": score}

    monkeypatch.setattr(composer, "judge_diff", _fake_judge)


def test_proposal_carries_grade_blast_and_validation(workspace, monkeypatch):
    _stub_judge(monkeypatch, score=8.5)
    # A minimal, valid diff to util.py's helper().
    diff = "@@ -1,2 +1,2 @@\n def helper():\n-    return 1\n+    return 2\n"
    _stub_generation(
        monkeypatch,
        {"summary": "bump helper", "edits": [
            {"path": "util.py", "unified_diff": diff, "rationale": "why", "confidence": 0.9},
        ]},
        meta={"provider": "cerebras", "cost_usd": 0.0004},
    )
    run = asyncio.run(
        composer.run_composer(
            "change helper", workspace_root=str(workspace),
            tenant_id="wtest", graph_key="wtest",
        )
    )
    assert run.run_id.startswith("cmp-")
    assert run.providers_tried == ["groq"]
    # Cost-HUD signals pass straight through to the editor.
    assert run.provider == "cerebras"
    assert run.cost_usd == 0.0004
    assert len(run.edits) == 1
    e = run.edits[0]
    assert e.judge_score == 8.5
    assert e.validation["valid"] is True
    assert e.dry_run_ok is True
    # helper() is called by a() → blast-radius finds the caller.
    assert e.blast_radius["found"] is True
    affected = {s["symbol"] for L in e.blast_radius["layers"] for s in L["symbols"]}
    assert "a" in affected


def test_broken_diff_is_high_risk_and_gated(workspace, monkeypatch):
    _stub_judge(monkeypatch, score=9.0)
    # Context that does not match the file → dry-run fails → high risk.
    bad = "@@ -1,2 +1,2 @@\n def helper():\n-    return 999\n+    return 2\n"
    _stub_generation(
        monkeypatch,
        {"summary": "x", "edits": [{"path": "util.py", "unified_diff": bad, "confidence": 0.5}]},
    )
    run = asyncio.run(
        composer.run_composer(
            "x", workspace_root=str(workspace), tenant_id="wtest", graph_key="wtest"
        )
    )
    e = run.edits[0]
    assert e.dry_run_ok is False
    assert run.risk == "high"
    assert run.requires_approval is True


def test_low_judge_score_gates_the_run(workspace, monkeypatch):
    _stub_judge(monkeypatch, score=3.0)  # below _JUDGE_LOW
    diff = "@@ -1,2 +1,2 @@\n def helper():\n-    return 1\n+    return 2\n"
    _stub_generation(
        monkeypatch,
        {"summary": "x", "edits": [{"path": "util.py", "unified_diff": diff, "confidence": 0.9}]},
    )
    run = asyncio.run(
        composer.run_composer(
            "x", workspace_root=str(workspace), tenant_id="wtest", graph_key="wtest"
        )
    )
    assert run.risk == "high"
    assert run.requires_approval is True


def test_no_provider_is_a_degraded_run(workspace, monkeypatch):
    _stub_generation(monkeypatch, {}, tried=())  # model produced nothing
    run = asyncio.run(
        composer.run_composer(
            "x", workspace_root=str(workspace), tenant_id="wtest", graph_key="wtest"
        )
    )
    assert run.degraded is True
    assert run.edits == []
    assert run.risk == "low"


def test_composer_mcp_tool_registered():
    from app.mcp.server import mcp_server

    names = {t.name for t in asyncio.run(mcp_server.list_tools())}
    assert "composer_propose" in names
