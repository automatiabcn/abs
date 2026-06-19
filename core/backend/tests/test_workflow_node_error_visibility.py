# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""3rd-eye audit — a workflow node that RAISES must not fail silently.

The linear engine catches a node exception so one failure can't abort the whole
run (best-effort). But it only surfaced `unsupported` nodes in `warnings`; a node
that *raised* had its error buried in `node_outputs[nid]` while the run still
reported a green `state == "done"`. A caller checking only `state` would think
everything succeeded. This pins that node failures appear in `warnings`.
"""

from __future__ import annotations

import asyncio

import app.workflow_v10.runner as runner


async def _run(wf):
    runner.reset_for_tests()
    job_id = await runner.enqueue(wf, "demo")
    for _ in range(50):
        await asyncio.sleep(0.01)
        st = runner.status(job_id)
        if st and st["state"] in ("done", "error"):
            return st
    return runner.status(job_id)


def _wf():
    return {
        "nodes": [
            {"id": "t", "kind": "trigger", "config": {"input": "x"}},
            {"id": "n1", "kind": "llm_call", "config": {"prompt_template": "hi"}},
        ],
        "edges": [{"source": "t", "target": "n1"}],
    }


def test_node_exception_surfaces_warning_not_silent_done(monkeypatch) -> None:
    orig = runner._run_node

    async def _boom(node, kind, outputs, tenant):  # noqa: ANN001
        if kind == "llm_call":
            raise RuntimeError("kaboom from provider")
        return await orig(node, kind, outputs, tenant)

    monkeypatch.setattr(runner, "_run_node", _boom)

    st = asyncio.run(_run(_wf()))
    # best-effort: the run still completes rather than aborting
    assert st["state"] == "done"
    # the error is recorded on the node…
    assert st["node_outputs"]["n1"].get("error")
    # …AND surfaced in warnings, so "done" doesn't hide it
    warnings = st.get("warnings") or []
    assert any("n1" in w and "failed" in w for w in warnings), warnings
