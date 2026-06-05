"""Workflow ``abs_tool`` node — real read-only ABS tool invocation.

Round B of the durable-engine follow-up. abs_tool used to be recorded as
skipped. It now invokes real internal tools by name (RAG query, system status,
ask*/cascade) and threads tool_args/upstream output in. External, side-effecting
names (slack_post, gmail_send) get an honest "not available — needs a plugin"
error instead of a faked success.
"""

import asyncio

import app.workflow_v10.runner as runner


async def _run(node, outputs=None):  # noqa: ANN001
    return await runner._run_node(node, "abs_tool", outputs or {}, "demo")


def test_rag_query_invokes_real_query(monkeypatch):
    seen = {}

    async def fake_query(question, top_k=5, **kw):  # noqa: ANN001
        seen["q"] = question
        seen["k"] = top_k
        return [{"snippet": "hit", "score": 0.9}]

    import app.rag as rag_mod

    monkeypatch.setattr(rag_mod, "query", fake_query)

    node = {
        "id": "t1",
        "kind": "abs_tool",
        "config": {"tool_name": "abs.rag_query", "tool_args": {"question": "what is {{n0}}", "top_k": 3}},
    }
    out = asyncio.run(_run(node, {"n0": {"text": "ABS"}}))
    assert out["kind"] == "abs_tool"
    assert seen["q"] == "what is ABS"  # templated
    assert seen["k"] == 3
    assert "hit" in out["text"]


def test_ask_routes_to_cascade(monkeypatch):
    captured = {}

    class _Resp:
        text = "CASCADE-OUT"

    async def fake_cascade(prompt, *, primary, tenant_id="_global", **kw):  # noqa: ANN001
        captured["prompt"] = prompt
        captured["primary"] = primary
        return _Resp()

    import app.cascade.orchestrator as orch

    monkeypatch.setattr(orch, "call_with_cascade", fake_cascade)

    node = {
        "id": "t1",
        "kind": "abs_tool",
        "config": {"tool_name": "ask_gptoss", "tool_args": {"prompt": "summarize {{n0}}"}},
    }
    out = asyncio.run(_run(node, {"n0": {"text": "the doc"}}))
    assert out["text"] == "CASCADE-OUT"
    assert captured["prompt"] == "summarize the doc"
    assert captured["primary"] == "gptoss"  # ask_<provider> → provider


def test_unknown_external_tool_is_honest_error():
    node = {
        "id": "t1",
        "kind": "abs_tool",
        "config": {"tool_name": "abs.gmail_send", "tool_args": {"to": "x@y.z"}},
    }
    out = asyncio.run(_run(node))
    assert "error" in out
    assert "not available" in out["error"]
    assert "plugin" in out["error"]
    assert "text" not in out  # never fakes a side-effect success


def test_empty_question_skipped():
    node = {"id": "t1", "kind": "abs_tool", "config": {"tool_name": "rag_query", "tool_args": {}}}
    out = asyncio.run(_run(node))
    assert out.get("skipped") == "abs_tool"
