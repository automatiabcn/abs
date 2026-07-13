from __future__ import annotations

import json

import pytest

from app.workflow_v10.builder.ontology import (
    Edge,
    Node,
    NodeConfig,
    NodeKind,
    Trigger,
    TriggerKind,
    Workflow,
)
from app.workflow_v10.builder.synthesizer import (
    SynthesisError,
    build_prompt,
    extract_json,
    synthesize,
)
from app.workflow_v10.builder.templates import get_template
from app.workflow_v10.builder.validator import (
    ValidationReport,
    schema_check,
    semantic_check,
    validate_workflow,
)


def _good_payload() -> dict:
    return get_template("rag-query-chat").workflow.model_dump(mode="json")


# ---- synthesizer ----------------------------------------------------------


def test_build_prompt_includes_intent_and_examples():
    prompt = build_prompt("Send Friday status report")
    assert "User intent (en): Send Friday status report" in prompt
    assert "Workflow JSON:" in prompt
    assert "Examples:" in prompt


def test_extract_json_passes_through_clean_object():
    payload = '{"foo": 1}'
    assert extract_json(payload) == payload


def test_extract_json_strips_prose_and_returns_object():
    text = 'Sure! Here is the JSON:\n{"a": 1, "b": [2, 3]}\nDone.'
    assert json.loads(extract_json(text)) == {"a": 1, "b": [2, 3]}


def test_extract_json_no_json_raises():
    with pytest.raises(SynthesisError):
        extract_json("just prose, no JSON object here")


async def test_synthesize_happy_path_first_try():
    payload = _good_payload()

    async def fake_synth(_prompt: str) -> str:
        return json.dumps(payload)

    res = await synthesize("any intent", synth_fn=fake_synth)
    assert res.revisions == 0
    assert res.workflow.id == payload["id"]


async def test_synthesize_revises_on_invalid_then_recovers():
    payload = _good_payload()
    calls = {"n": 0}

    async def fake_synth(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "not even json"
        return json.dumps(payload)

    res = await synthesize("retry intent", synth_fn=fake_synth, max_revisions=2)
    assert res.revisions == 1
    assert calls["n"] == 2


async def test_synthesize_exhausts_revisions_raises():
    async def fake_synth(_prompt: str) -> str:
        return "garbage"

    with pytest.raises(SynthesisError):
        await synthesize("bad intent", synth_fn=fake_synth, max_revisions=1)


# ---- validator: schema_check ----------------------------------------------


def test_schema_check_valid_payload():
    wf, errs = schema_check(_good_payload())
    assert wf is not None and errs == []


def test_schema_check_invalid_payload_returns_errors():
    wf, errs = schema_check({"id": "wf-1"})  # missing required fields
    assert wf is None and errs


# ---- validator: semantic_check --------------------------------------------


def _wf_with(
    nodes: list[Node], edges: list[Edge], *, tenant_scoped: bool = True
) -> Workflow:
    return Workflow(
        id="wf-x",
        name="X",
        description="d",
        tenant_scoped=tenant_scoped,
        trigger=Trigger(kind=TriggerKind.MANUAL, id="trg-x"),
        nodes=nodes,
        edges=edges,
    )


def test_semantic_check_destructive_without_hitl_errors():
    nodes = [
        Node(id="step-a", kind=NodeKind.LLM_CALL, name="Compose"),
        Node(
            id="step-b",
            kind=NodeKind.ABS_TOOL,
            name="Send",
            config=NodeConfig(tool_name="abs.gmail_send"),
        ),
    ]
    edges = [Edge(source="step-a", target="step-b")]
    wf = _wf_with(nodes, edges)
    errors, _warnings = semantic_check(wf)
    assert any("HITL approval" in e for e in errors)


def test_semantic_check_destructive_with_hitl_passes():
    nodes = [
        Node(id="step-a", kind=NodeKind.LLM_CALL, name="Compose"),
        Node(
            id="step-b",
            kind=NodeKind.HITL,
            name="Approve",
            config=NodeConfig(approval_role="tenant_owner"),
        ),
        Node(
            id="step-c",
            kind=NodeKind.ABS_TOOL,
            name="Send",
            config=NodeConfig(tool_name="abs.gmail_send"),
        ),
    ]
    edges = [
        Edge(source="step-a", target="step-b"),
        Edge(source="step-b", target="step-c"),
    ]
    wf = _wf_with(nodes, edges)
    errors, _ = semantic_check(wf)
    assert not any("HITL approval" in e for e in errors)


def test_semantic_check_unreachable_node_errors():
    nodes = [
        Node(id="step-a", kind=NodeKind.LLM_CALL, name="A"),
        Node(id="step-b", kind=NodeKind.OUTPUT, name="B"),
        Node(id="step-c", kind=NodeKind.OUTPUT, name="C"),
    ]
    edges = [Edge(source="step-a", target="step-b")]
    wf = _wf_with(nodes, edges)
    errors, _ = semantic_check(wf)
    assert any("unreachable" in e for e in errors)


def test_semantic_check_warns_on_rag_without_cerbos():
    nodes = [
        Node(
            id="step-a",
            kind=NodeKind.ABS_TOOL,
            name="RAG",
            config=NodeConfig(tool_name="abs.rag_query"),
        ),
        Node(id="step-b", kind=NodeKind.OUTPUT, name="Out"),
    ]
    edges = [Edge(source="step-a", target="step-b")]
    wf = _wf_with(nodes, edges, tenant_scoped=True)
    _errors, warnings = semantic_check(wf)
    assert any("cerbos" in w.lower() for w in warnings)


def test_semantic_check_destructive_post_requires_hitl():
    nodes = [
        Node(id="step-a", kind=NodeKind.LLM_CALL, name="Compose"),
        Node(
            id="step-b",
            kind=NodeKind.API_REQUEST,
            name="POST",
            config=NodeConfig(method="POST", url="https://example/api"),
        ),
    ]
    edges = [Edge(source="step-a", target="step-b")]
    wf = _wf_with(nodes, edges)
    errors, _ = semantic_check(wf)
    assert any("HITL approval" in e for e in errors)


# ---- validate_workflow integration ----------------------------------------


def test_validate_workflow_accepts_known_template():
    rep = validate_workflow(_good_payload())
    assert isinstance(rep, ValidationReport)
    assert rep.ok and not rep.errors


def test_validate_workflow_rejects_destructive_without_hitl():
    payload = {
        "id": "wf-bad",
        "name": "bad",
        "description": "d",
        "trigger": {"kind": "manual", "id": "trg-x", "description": ""},
        "tenant_scoped": True,
        "nodes": [
            {
                "id": "step-a",
                "kind": "abs_tool",
                "name": "send",
                "config": {"tool_name": "abs.gmail_send"},
                "retry_max": 0,
                "timeout_s": 60,
            }
        ],
        "edges": [],
        "variables": [],
        "tags": [],
        "locale": "en",
    }
    rep = validate_workflow(payload)
    assert not rep.ok
    assert any("HITL approval" in e for e in rep.errors)


def test_validate_workflow_schema_failure_returns_errors():
    rep = validate_workflow({"id": "wf-1"})
    assert not rep.ok and rep.errors
