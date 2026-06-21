"""HITL approval-role enforcement (repo audit follow-up).

Before: runner.resume recorded any caller's approval and the API passed the
caller's *email* as "role", so a member could approve a gate that templates
mark approval_role="tenant_owner". Now the approver's resolved role is enforced
against the gate, and an insufficient role leaves the gate pending.
"""

from __future__ import annotations

import asyncio

from app.workflow_v10 import runner


_GATED_WF = {
    "nodes": [
        {"id": "t", "kind": "trigger", "config": {"input": "go"}},
        {"id": "gate", "kind": "hitl", "config": {"approval_role": "tenant_owner"}},
        {"id": "act", "kind": "output", "config": {"output_template": "done: {{t}}"}},
    ],
    "edges": [
        {"source": "t", "target": "gate"},
        {"source": "gate", "target": "act"},
    ],
}


async def _enqueue_until_pause() -> str:
    runner.reset_for_tests()
    job_id = await runner.enqueue(_GATED_WF, "demo")
    for _ in range(100):
        await asyncio.sleep(0.01)
        if runner.status(job_id)["state"] == "awaiting_approval":
            return job_id
    raise AssertionError("workflow never paused at the hitl gate")


def test_member_cannot_approve_owner_gate_and_gate_stays_pending():
    async def go():
        job_id = await _enqueue_until_pause()

        # member is below tenant_owner → rejected, no decision recorded
        res = await runner.resume(job_id, approved=True, role="member", actor="m@x.com")
        assert res["error"] == "approval_role_required"
        assert res["required_role"] == "tenant_owner"
        # gate is still pending — an authorised approver can still act
        assert runner.status(job_id)["state"] == "awaiting_approval"
        assert runner.status(job_id)["pending_node"] == "gate"

        # admin (== owner tier) approves → run completes
        ok = await runner.resume(job_id, approved=True, role="admin", actor="a@x.com")
        assert ok["approved"] is True
        for _ in range(100):
            await asyncio.sleep(0.01)
            if runner.status(job_id)["state"] == "done":
                break
        st = runner.status(job_id)
        assert st["state"] == "done"
        assert st["node_outputs"]["act"]["text"] == "done: go"
        # audit trail records the approver identity
        assert st["node_outputs"]["gate"]["approved_by"] == "a@x.com"

    asyncio.run(go())


def test_manager_satisfies_manager_gate_but_not_owner():
    from app.workflow_v10.runner import _role_satisfies

    assert _role_satisfies("manager", "manager") is True
    assert _role_satisfies("manager", "tenant_owner") is False
    assert _role_satisfies("admin", "tenant_owner") is True
    assert _role_satisfies("member", "manager") is False
    # no required role → legacy hitl node, anyone may approve
    assert _role_satisfies("member", None) is True
    # unknown required role fails closed to the top tier
    assert _role_satisfies("manager", "wizard") is False
    assert _role_satisfies("admin", "wizard") is True


def test_unknown_node_kind_is_explicit_unsupported_error():
    async def go():
        wf = {
            "nodes": [{"id": "x", "kind": "teleport", "config": {}}],
            "edges": [],
        }
        runner.reset_for_tests()
        job_id = await runner.enqueue(wf, "demo")
        for _ in range(100):
            await asyncio.sleep(0.01)
            if runner.status(job_id)["state"] in ("done", "error"):
                break
        out = runner.status(job_id)["node_outputs"]["x"]
        assert out.get("unsupported") is True
        assert "teleport" in out.get("error", "")

    asyncio.run(go())
