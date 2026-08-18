"""Judgments belong to the tenant that made them; server-wide readouts belong
to the operator.

Audit 2026-08-18: judge_recent handed every tenant's file paths and teaching
to any token, judge_outcome let anyone flip anyone's record (the training
signal), judge_persona_train retuned the persona every tenant's scores use,
workflow_status/resume and admin_overview answered any token.
"""

from __future__ import annotations

import json

import pytest

from app.judge import log as jlog


@pytest.fixture
def judge_log(tmp_path, monkeypatch):
    p = tmp_path / "judge_log.jsonl"
    monkeypatch.setattr(jlog, "_log_path", lambda: p)
    a = jlog.log_judgment({"combined_score": 8.0}, file_path="acme/a.py", tenant="acme")
    b = jlog.log_judgment({"combined_score": 3.0}, file_path="globex/b.py", tenant="globex")
    # a record from before the field existed
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "legacy1", "ts": 1.0, "file": "old.py", "combined_score": 5.0, "outcome": None}) + "\n")
    return {"a": a, "b": b, "path": p}


def test_a_tenant_reads_only_its_own_judgments(judge_log):
    assert [e["file"] for e in jlog.read_recent(tenant="acme")] == ["acme/a.py"]
    assert [e["file"] for e in jlog.read_recent(tenant="globex")] == ["globex/b.py"]


def test_legacy_records_are_visible_to_the_default_view_only(judge_log):
    assert "old.py" in [e["file"] for e in jlog.read_recent(tenant="default")]
    assert "old.py" not in [e["file"] for e in jlog.read_recent(tenant="acme")]
    assert len(jlog.read_recent(tenant=None)) == 3


def test_a_tenant_cannot_flip_another_tenants_outcome(judge_log):
    assert jlog.update_outcome(judge_log["b"], "accept", tenant="acme") is False
    assert jlog.update_outcome(judge_log["b"], "accept", tenant="globex") is True
    rows = {e["id"]: e for e in jlog.read_recent(tenant=None)}
    assert rows[judge_log["b"]]["outcome"] == "accept"
    assert rows[judge_log["a"]]["outcome"] is None


def test_the_record_carries_the_mcp_callers_tenant(tmp_path, monkeypatch):
    p = tmp_path / "j.jsonl"
    monkeypatch.setattr(jlog, "_log_path", lambda: p)
    from app.mcp.context import mcp_tenant_id

    tok = mcp_tenant_id.set("acme")
    try:
        jlog.log_judgment({"combined_score": 1.0}, file_path="x.py")
    finally:
        mcp_tenant_id.reset(tok)
    assert jlog.read_recent(tenant=None)[0]["tenant"] == "acme"


@pytest.mark.asyncio
async def test_judge_tools_scope_by_the_calling_token(judge_log, monkeypatch):
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import judge_extras as jt

    monkeypatch.setattr(jt, "_tenant", lambda: "acme")
    recent = json.loads(await jt.judge_recent())
    assert [e["file"] for e in recent] == ["acme/a.py"]
    out = json.loads(await jt.judge_outcome(judge_log["b"], "reject"))
    assert out["ok"] is False


@pytest.mark.parametrize(
    "module,tool,args",
    [
        ("app.mcp.tools.judge_persona", "judge_persona_train", {}),
        ("app.mcp.tools.judge_persona", "judge_persona_reset", {}),
        ("app.mcp.tools.workflow", "workflow_status", {}),
        ("app.mcp.tools.workflow", "workflow_resume", {"trace_id": "t"}),
        ("app.mcp.tools.admin_tools", "admin_overview", {}),
    ],
)
@pytest.mark.asyncio
async def test_server_wide_tools_refuse_a_member(module, tool, args, monkeypatch):
    import importlib

    import app.mcp.server  # noqa: F401

    mod = importlib.import_module(module)
    from app.config import settings

    monkeypatch.setattr(settings, "admin_email", "owner@example.com", raising=False)
    from app.mcp.context import mcp_tenant_id, mcp_user_subject

    t1 = mcp_tenant_id.set("acme")
    t2 = mcp_user_subject.set("member@example.com")
    try:
        out = json.loads(await getattr(mod, tool)(**args))
    finally:
        mcp_tenant_id.reset(t1)
        mcp_user_subject.reset(t2)
    assert out.get("error") == "operator_only", out
    assert "operator" in out["detail"]


@pytest.mark.asyncio
async def test_the_operator_still_reads_the_dashboard(monkeypatch):
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import workflow as wt
    from app.config import settings

    monkeypatch.setattr(settings, "admin_email", "owner@example.com", raising=False)
    monkeypatch.setattr(wt, "stats", lambda: {"total": 0})
    monkeypatch.setattr(wt, "list_workflows", lambda **k: [])
    from app.mcp.context import mcp_tenant_id, mcp_user_subject

    t1 = mcp_tenant_id.set("default")
    t2 = mcp_user_subject.set("Owner@Example.com")
    try:
        out = json.loads(await wt.workflow_status())
    finally:
        mcp_tenant_id.reset(t1)
        mcp_user_subject.reset(t2)
    assert "error" not in out and out["total"] == 0
