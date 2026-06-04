"""Workflow runner — Phase-1.5 real linear execution.

The runner used to `_simulate_run` (sleep then mark done). It now actually
executes `llm_call` nodes via the cascade and threads `{{node_id}}` outputs
into downstream prompts. Non-LLM kinds are recorded (the durable engine —
HITL/loop/abs_tool — is a follow-up). A single node failing must not abort
the whole run.
"""

import asyncio



import app.cascade.orchestrator as orch
import app.workflow_v10.runner as runner


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


async def _run(wf: dict, tenant: str = "demo") -> dict:
    runner.reset_for_tests()
    job_id = await runner.enqueue(wf, tenant)
    for _ in range(40):  # let the background task finish
        await asyncio.sleep(0.02)
        st = runner.status(job_id)
        if st and st["state"] in ("done", "error"):
            return st
    return runner.status(job_id)


def test_llm_call_chain_executes_and_templates(monkeypatch):
    calls: list[str] = []

    async def fake(prompt, *, primary, model=None, **kw):  # noqa: ANN001
        calls.append(prompt)
        return _Resp("HELLO" if "say hello" in prompt else f"OUT[{prompt[:24]}]")

    monkeypatch.setattr(orch, "call_with_cascade", fake)

    wf = {
        "nodes": [
            {"id": "n1", "kind": "llm_call", "config": {"prompt_template": "say hello", "provider": "groq"}},
            {"id": "n2", "kind": "llm_call", "config": {"prompt_template": "translate: {{n1}}", "provider": "gemini"}},
        ],
        "edges": [{"source": "n1", "target": "n2"}],
    }
    st = asyncio.run(_run(wf))

    assert st["state"] == "done"
    assert st["node_outputs"]["n1"]["text"] == "HELLO"
    # n2's prompt must have seen n1's output (real chaining, not simulation).
    assert "HELLO" in calls[1]
    assert "HELLO" in st["node_outputs"]["n2"]["text"]


def test_node_failure_is_isolated_not_fatal(monkeypatch):
    async def boom(prompt, *, primary, model=None, **kw):  # noqa: ANN001
        raise RuntimeError("provider down")

    monkeypatch.setattr(orch, "call_with_cascade", boom)

    wf = {
        "nodes": [{"id": "n1", "kind": "llm_call", "config": {"prompt_template": "x", "provider": "groq"}}],
        "edges": [],
    }
    st = asyncio.run(_run(wf))
    # The run completes; the bad node carries an error rather than crashing it.
    assert st["state"] == "done"
    assert "error" in st["node_outputs"]["n1"]


def test_non_llm_kinds_recorded_not_faked():
    wf = {
        "nodes": [
            {"id": "h1", "kind": "hitl", "config": {}},
            {"id": "o1", "kind": "output", "config": {}},
        ],
        "edges": [{"source": "h1", "target": "o1"}],
    }
    st = asyncio.run(_run(wf))
    assert st["state"] == "done"
    assert st["node_outputs"]["h1"].get("skipped") == "hitl"
