"""Workflow ``hitl`` node — human-in-the-loop pause / approve / reject.

Round D. A hitl node pauses the whole run (state=awaiting_approval). resume()
approves (already-run nodes reused, downstream executes) or rejects (downstream
left unreached). A run must never auto-pass a hitl gate.
"""

import asyncio

import app.workflow_v10.runner as runner


async def _start(wf):
    runner.reset_for_tests()
    job_id = await runner.enqueue(wf, "demo")
    for _ in range(50):
        await asyncio.sleep(0.01)
        st = runner.status(job_id)
        if st and st["state"] in ("done", "error", "awaiting_approval"):
            return job_id, st
    return job_id, runner.status(job_id)


def _hitl_wf():
    return {
        "nodes": [
            {"id": "t", "kind": "trigger", "config": {"input": "deploy"}},
            {"id": "gate", "kind": "hitl", "config": {"approval_role": "admin"}},
            {
                "id": "act",
                "kind": "output",
                "config": {"output_template": "ACTED on {{t}}"},
            },
        ],
        "edges": [
            {"source": "t", "target": "gate"},
            {"source": "gate", "target": "act"},
        ],
    }


def test_pauses_at_hitl_and_does_not_run_downstream():
    async def go():
        job_id, st = await _start(_hitl_wf())
        assert st["state"] == "awaiting_approval"
        assert st["pending_node"] == "gate"
        assert st["node_outputs"]["gate"]["awaiting"] == "approval"
        # downstream must NOT have executed
        assert "act" not in st["node_outputs"]
        return job_id

    asyncio.run(go())


def test_approve_resumes_and_runs_downstream():
    async def go():
        job_id, st = await _start(_hitl_wf())
        assert st["state"] == "awaiting_approval"
        res = await runner.resume(job_id, approved=True, role="admin")
        assert res["approved"] is True
        final = runner.status(job_id)
        assert final["state"] == "done"
        assert final["node_outputs"]["gate"]["approved"] is True
        assert final["node_outputs"]["act"]["text"] == "ACTED on deploy"

    asyncio.run(go())


def test_reject_finishes_without_downstream():
    async def go():
        job_id, st = await _start(_hitl_wf())
        res = await runner.resume(job_id, approved=False, role="admin")
        assert res["approved"] is False
        final = runner.status(job_id)
        assert final["state"] == "done"
        assert final["node_outputs"]["gate"]["rejected"] is True
        # act was downstream of a rejected gate → never reached
        assert (
            final["node_outputs"].get("act", {}).get("skipped") == "unreached"
            or "act" not in final["node_outputs"]
        )

    asyncio.run(go())


def test_resume_non_paused_job_is_conflict():
    async def go():
        # a workflow with no hitl finishes immediately
        wf = {
            "nodes": [
                {"id": "o", "kind": "output", "config": {"output_template": "x"}}
            ],
            "edges": [],
        }
        runner.reset_for_tests()
        job_id = await runner.enqueue(wf, "demo")
        for _ in range(50):
            await asyncio.sleep(0.01)
            if runner.status(job_id)["state"] == "done":
                break
        res = await runner.resume(job_id, approved=True)
        assert "error" in res

    asyncio.run(go())


def test_resume_unknown_job_returns_none():
    asyncio.run(_assert_none())


async def _assert_none():
    runner.reset_for_tests()
    assert await runner.resume("nope", approved=True) is None
