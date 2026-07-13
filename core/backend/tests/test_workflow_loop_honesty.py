"""Non-working-feature round — a `loop` node must NOT masquerade as success.

The linear v1 engine cannot iterate. Previously a `loop` node returned a silent
`{"skipped": "loop"}` and the run finished as a clean `done`, so a workflow built
from the shipped "Each supplier" template (templates.py) reported success while
the loop body ran ZERO times — it notified nobody. This pins the honest
behaviour: the loop node surfaces an explicit `unsupported` error and the run
records a visible `warnings` entry, so the gap is reported rather than hidden.
Real iteration is the durable-engine follow-up.
"""

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


def _loop_wf():
    return {
        "nodes": [
            {"id": "t", "kind": "trigger", "config": {"input": "suppliers"}},
            {
                "id": "lp",
                "kind": "loop",
                "config": {"script": "for s in suppliers: notify"},
            },
            {"id": "out", "kind": "output", "config": {"output_template": "done"}},
        ],
        "edges": [
            {"source": "t", "target": "lp"},
            {"source": "lp", "target": "out"},
        ],
    }


def test_loop_node_reports_unsupported_not_silent_skip():
    st = asyncio.run(_run(_loop_wf()))
    # The run still completes (one node failing doesn't abort), but the loop
    # node must be honestly flagged, not silently skipped.
    lp = st["node_outputs"]["lp"]
    assert lp.get("unsupported") is True, lp
    assert "skipped" not in lp, "loop must not look like a normal skip"
    assert "zero iterations" in lp.get("error", "")


def test_loop_run_surfaces_warning():
    st = asyncio.run(_run(_loop_wf()))
    warnings = st.get("warnings") or []
    assert any("lp" in w and "loop" in w for w in warnings), warnings
