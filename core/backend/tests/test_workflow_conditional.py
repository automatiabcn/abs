"""Workflow ``conditional`` node — safe evaluation + edge-condition routing.

Round C. conditional nodes evaluate a sandboxed boolean expression (never
eval()) and the runner routes reachability through labelled edges. The critical
invariant: a workflow with NO edge conditions runs every node exactly as before.
"""

import asyncio

import pytest

import app.workflow_v10.condition_eval as ce
import app.workflow_v10.runner as runner


# ---- safe condition evaluation ---------------------------------------------


def test_eval_string_equality():
    assert ce.evaluate('{{n1}} == "yes"', {"n1": {"text": "yes"}}) is True
    assert ce.evaluate('{{n1}} == "yes"', {"n1": {"text": "no"}}) is False


def test_eval_numeric_coercion():
    assert ce.evaluate("{{score}} >= 5", {"score": {"text": "7"}}) is True
    assert ce.evaluate("{{score}} >= 5", {"score": {"text": "3"}}) is False


def test_eval_membership_and_boolop():
    out = {"n1": {"text": "got an error here"}, "ok": {"text": "yes"}}
    assert ce.evaluate('"error" in {{n1}}', out) is True
    assert ce.evaluate('"error" in {{n1}} and {{ok}} == "yes"', out) is True
    assert ce.evaluate('"error" in {{n1}} and {{ok}} == "no"', out) is False


def test_eval_empty_is_true():
    assert ce.evaluate("", {}) is True


def test_eval_uses_result_of_conditional_upstream():
    # a {{ref}} to a conditional node resolves to its bool result
    assert (
        ce.evaluate('{{c1}} == "true"', {"c1": {"result": True, "text": "true"}})
        is True
    )


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('x')",
        "open('/etc/passwd').read()",
        "len({{n1}}) > 0",  # function call
        "n1 == 'x'",  # bare name (not a literal)
        "{{n1}}.__class__",  # attribute access
    ],
)
def test_eval_rejects_dangerous(expr):
    with pytest.raises(ce.ConditionError):
        ce.evaluate(expr, {"n1": {"text": "x"}})


# ---- edge-condition routing -------------------------------------------------


async def _run(wf):
    runner.reset_for_tests()
    job_id = await runner.enqueue(wf, "demo")
    for _ in range(50):
        await asyncio.sleep(0.01)
        st = runner.status(job_id)
        if st and st["state"] in ("done", "error"):
            return st
    return runner.status(job_id)


def _branch_wf(input_text):
    return {
        "nodes": [
            {"id": "t", "kind": "trigger", "config": {"input": input_text}},
            {
                "id": "c",
                "kind": "conditional",
                "config": {"condition_expr": '{{t}} == "go"'},
            },
            {"id": "yes", "kind": "output", "config": {"output_template": "took TRUE"}},
            {"id": "no", "kind": "output", "config": {"output_template": "took FALSE"}},
        ],
        "edges": [
            {"source": "t", "target": "c"},
            {"source": "c", "target": "yes", "condition": "true"},
            {"source": "c", "target": "no", "condition": "false"},
        ],
    }


def test_true_branch_taken_false_unreached():
    st = asyncio.run(_run(_branch_wf("go")))
    assert st["state"] == "done"
    assert st["node_outputs"]["c"]["result"] is True
    assert st["node_outputs"]["yes"]["text"] == "took TRUE"
    assert st["node_outputs"]["no"].get("skipped") == "unreached"


def test_false_branch_taken_true_unreached():
    st = asyncio.run(_run(_branch_wf("stop")))
    assert st["state"] == "done"
    assert st["node_outputs"]["c"]["result"] is False
    assert st["node_outputs"]["no"]["text"] == "took FALSE"
    assert st["node_outputs"]["yes"].get("skipped") == "unreached"


def test_diamond_join_reachable_via_any_path():
    # cond true → b runs, c unreached, but the join d is still reached through
    # b's unconditional edge (OR semantics — any firing edge reaches a node).
    wf = {
        "nodes": [
            {
                "id": "a",
                "kind": "conditional",
                "config": {"condition_expr": '"x" == "x"'},
            },
            {"id": "b", "kind": "output", "config": {"output_template": "B"}},
            {"id": "c", "kind": "output", "config": {"output_template": "C"}},
            {"id": "d", "kind": "output", "config": {"output_template": "D"}},
        ],
        "edges": [
            {"source": "a", "target": "b", "condition": "true"},
            {"source": "a", "target": "c", "condition": "false"},
            {"source": "b", "target": "d"},
            {"source": "c", "target": "d"},
        ],
    }
    st = asyncio.run(_run(wf))
    assert st["node_outputs"]["b"]["text"] == "B"
    assert st["node_outputs"]["c"].get("skipped") == "unreached"
    assert st["node_outputs"]["d"]["text"] == "D"  # join still runs


def test_cycle_does_not_hang():
    # a back-edge must not cause re-execution or an infinite loop.
    wf = {
        "nodes": [
            {"id": "t", "kind": "trigger", "config": {"input": "go"}},
            {"id": "a", "kind": "output", "config": {"output_template": "A"}},
            {"id": "b", "kind": "output", "config": {"output_template": "B"}},
        ],
        "edges": [
            {"source": "t", "target": "a"},
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},
        ],
    }
    st = asyncio.run(_run(wf))
    assert st["state"] == "done"
    assert st["node_outputs"]["a"]["text"] == "A"
    assert st["node_outputs"]["b"]["text"] == "B"


def test_no_conditions_runs_every_node_backwards_compat():
    wf = {
        "nodes": [
            {"id": "t", "kind": "trigger", "config": {"input": "x"}},
            {"id": "a", "kind": "output", "config": {"output_template": "A"}},
            {"id": "b", "kind": "output", "config": {"output_template": "B"}},
        ],
        "edges": [{"source": "t", "target": "a"}, {"source": "a", "target": "b"}],
    }
    st = asyncio.run(_run(wf))
    assert st["state"] == "done"
    # every node executed — no "unreached" anywhere
    assert all(
        "skipped" not in v or v.get("skipped") != "unreached"
        for v in st["node_outputs"].values()
    )
    assert st["node_outputs"]["a"]["text"] == "A"
    assert st["node_outputs"]["b"]["text"] == "B"
