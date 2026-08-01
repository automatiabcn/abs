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


def _stub_generation(monkeypatch, parsed, tried=("groq",), meta=None, seen=None):
    async def _fake(task, *, tenant_id, project_slug, user_subject, files=None, contents=None):
        if seen is not None:
            seen["files"] = files
            seen["contents"] = contents
        return parsed, list(tried), dict(meta or {})

    monkeypatch.setattr(composer, "_generate_edits", _fake)


def _stub_judge(monkeypatch, score=8.0, llm=None, ast=None, teaching=None):
    async def _fake_judge(diff, path=None, **_caller):
        return {
            "combined_score": score,
            "llm_score": llm if llm is not None else score,
            "ast_score": ast,
            "teaching": teaching or [],
        }

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


def test_composer_indexes_the_workspace_itself(tmp_path, monkeypatch):
    """Live tour: the blast-radius badge never appeared because the graph is
    only ever QUERIED here — on a workspace nobody ran code_graph_build on it
    stayed empty, silently dropping the signal that makes a proposal
    trustworthy. run_composer must index before it asks."""
    monkeypatch.setattr(codegraph.settings, "data_dir", str(tmp_path / "data"))
    ws = tmp_path / "fresh"
    ws.mkdir()
    (ws / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (ws / "app.py").write_text("def a():\n    return helper()\n", encoding="utf-8")
    # NOTE: no codegraph.build() here — that is the whole point.

    _stub_judge(monkeypatch, score=8.0)
    diff = "@@ -1,2 +1,2 @@\n def helper():\n-    return 1\n+    return 2\n"
    _stub_generation(
        monkeypatch,
        {"summary": "s", "edits": [{"path": "util.py", "unified_diff": diff}]},
    )
    run = asyncio.run(
        composer.run_composer(
            "x", workspace_root=str(ws), tenant_id="fresh", graph_key="freshkey"
        )
    )
    blast = run.edits[0].blast_radius
    assert blast.get("found") is True, "blast-radius empty on an unindexed workspace"
    assert blast.get("total_affected", 0) >= 1


def test_a_style_gap_does_not_gate_a_correct_edit(workspace, monkeypatch):
    """The gate exists to stop DANGEROUS changes reaching the developer
    unreviewed. Measured live: a correct minimal edit scored 8.0 from the model
    and 0.0 from the style fingerprint, blending to 3.2 — and the run was gated
    as high risk for having no docstring."""
    _stub_judge(monkeypatch, score=3.2, llm=8.0, ast=0.0,
                teaching=["docstring_ratio: 0.00 vs target 0.60"])
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
    assert run.risk == "low", "style is advice, not danger"
    assert run.requires_approval is False
    e = run.edits[0]
    assert e.judge_score == 3.2 and e.judge_correctness == 8.0 and e.judge_style == 0.0
    assert e.judge_notes, "the style note must still travel with the edit"


def test_a_real_correctness_problem_still_gates(workspace, monkeypatch):
    _stub_judge(monkeypatch, score=2.0, llm=2.0, ast=2.0)
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
    assert run.risk == "high" and run.requires_approval is True


def test_without_a_model_leg_the_blend_still_gates(workspace, monkeypatch):
    """No correctness signal is not permission to wave an edit through."""
    _stub_judge(monkeypatch, score=3.0, llm=None, ast=3.0)

    async def _judge_no_llm(diff, path=None, **_caller):
        return {"combined_score": 3.0, "llm_score": None, "ast_score": 3.0, "teaching": []}

    monkeypatch.setattr(composer, "judge_diff", _judge_no_llm)
    diff = "@@ -1,2 +1,2 @@\n def helper():\n-    return 1\n+    return 2\n"
    _stub_generation(
        monkeypatch,
        {"summary": "x", "edits": [{"path": "util.py", "unified_diff": diff}]},
    )
    run = asyncio.run(
        composer.run_composer(
            "x", workspace_root=str(workspace), tenant_id="wtest", graph_key="wtest"
        )
    )
    assert run.risk == "high"


def test_the_model_is_told_which_files_exist(workspace, monkeypatch):
    """A model asked for a "workspace-relative path" and never shown the
    workspace invents plausible ones — a live run proposed src/utils.js in a
    workspace whose only files were util.py and app.py."""
    _stub_judge(monkeypatch, score=8.0)
    seen: dict = {}
    diff = "@@ -1,2 +1,2 @@\n def helper():\n-    return 1\n+    return 2\n"
    _stub_generation(
        monkeypatch,
        {"summary": "x", "edits": [{"path": "util.py", "unified_diff": diff}]},
        seen=seen,
    )
    asyncio.run(
        composer.run_composer(
            "x", workspace_root=str(workspace), tenant_id="wtest", graph_key="wtest"
        )
    )
    assert sorted(seen["files"]) == ["app.py", "util.py"]


def test_workspace_listing_skips_the_directories_nobody_edits(tmp_path):
    import os

    ws = tmp_path / "ws"
    (ws / "node_modules" / "left-pad").mkdir(parents=True)
    (ws / "node_modules" / "left-pad" / "index.js").write_text("x", encoding="utf-8")
    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("x", encoding="utf-8")
    (ws / "src").mkdir()
    (ws / "src" / "main.py").write_text("x", encoding="utf-8")
    (ws / "logo.png").write_bytes(b"\x89PNG")

    assert composer.workspace_files(str(ws)) == [os.path.join("src", "main.py")]


def test_the_prompt_names_the_files_and_forbids_inventing_one():
    prompt = composer._prompt("do something", ["util.py", "app.py"])
    assert "util.py" in prompt and "app.py" in prompt
    assert "do not invent a path" in prompt


def test_a_truncated_listing_says_so():
    """Telling a model "these are the files" when the list was cut off is a
    false statement about the workspace."""
    many = [f"f{i}.py" for i in range(composer._MAX_LISTED_FILES)]
    assert "stops at" in composer._prompt("t", many)
    assert "stops at" not in composer._prompt("t", ["only.py"])


def test_a_missing_file_is_refused_with_the_reason_named(workspace, monkeypatch):
    """The editor renders validation.reason; the engine must keep saying which
    stage refused, so the badge can read "not in this workspace" instead of the
    outcome ("dry-run failed")."""
    _stub_judge(monkeypatch, score=8.0)
    diff = "@@ -1,2 +1,2 @@\n def helper():\n-    return 1\n+    return 2\n"
    _stub_generation(
        monkeypatch,
        {"summary": "x", "edits": [{"path": "src/utils.js", "unified_diff": diff}]},
    )
    run = asyncio.run(
        composer.run_composer(
            "x", workspace_root=str(workspace), tenant_id="wtest", graph_key="wtest"
        )
    )
    edit = run.edits[0]
    assert edit.dry_run_ok is False
    assert edit.validation["valid"] is False
    assert "no such file" in edit.validation["reason"]


def test_the_model_is_shown_the_lines_it_must_match(workspace, monkeypatch):
    """Knowing a file's name is not knowing its lines: given only a listing the
    model wrote a diff against the file it imagined — right path, invented
    context, patch refused (measured live: valid=True, dry_run_ok=False)."""
    _stub_judge(monkeypatch, score=8.0)
    seen: dict = {}
    diff = "@@ -1,2 +1,2 @@\n def helper():\n-    return 1\n+    return 2\n"
    _stub_generation(
        monkeypatch,
        {"summary": "x", "edits": [{"path": "util.py", "unified_diff": diff}]},
        seen=seen,
    )
    asyncio.run(
        composer.run_composer(
            "make helper return 2",
            workspace_root=str(workspace),
            tenant_id="wtest",
            graph_key="wtest",
        )
    )
    sent = dict(seen["contents"])
    assert "util.py" in sent
    assert "def helper():" in sent["util.py"], "the real lines, not just the name"


def test_the_file_the_task_names_is_ranked_first(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "billing.py").write_text("def charge():\n    pass\n", encoding="utf-8")
    (ws / "unrelated.py").write_text("def other():\n    pass\n", encoding="utf-8")
    ranked = composer.relevant_files(
        str(ws), "fix the charge in billing", ["unrelated.py", "billing.py"]
    )
    assert ranked[0][0] == "billing.py"


def test_context_stays_inside_its_budget(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    names = []
    for i in range(30):
        name = f"f{i:02d}.py"
        (ws / name).write_text("x = 1\n" * 400, encoding="utf-8")
        names.append(name)
    picked = composer.relevant_files(str(ws), "touch f00", names)
    assert len(picked) <= composer._MAX_CONTEXT_FILES
    assert sum(len(b) for _, b in picked) <= composer._MAX_CONTEXT_CHARS


def test_the_prompt_carries_the_current_lines():
    prompt = composer._prompt("t", ["util.py"], [("util.py", "def helper():\n    return 1\n")])
    assert "def helper():" in prompt
    assert "character for character" in prompt
