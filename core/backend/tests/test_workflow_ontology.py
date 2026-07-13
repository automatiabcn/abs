from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.workflow_v10.builder.ontology import (
    Edge,
    EdgeKind,
    Node,
    NodeConfig,
    NodeKind,
    Trigger,
    TriggerKind,
    Variable,
    VariableScope,
    Workflow,
    WorkflowTemplate,
    build_simple_chain,
)
from app.workflow_v10.builder.templates import (
    TEMPLATES,
    get_template,
    list_templates,
)


def _wf_kwargs(**overrides):
    base = dict(
        id="wf-1",
        name="Demo",
        description="d",
        trigger=Trigger(kind=TriggerKind.WEBHOOK, id="trg-1", webhook_path="/x"),
        nodes=[
            Node(id="n1", kind=NodeKind.LLM_CALL, name="Step 1"),
            Node(id="n2", kind=NodeKind.OUTPUT, name="Step 2"),
        ],
        edges=[Edge(source="n1", target="n2")],
    )
    base.update(overrides)
    return base


def test_trigger_cron_requires_cron_expr():
    with pytest.raises(ValidationError):
        Trigger(kind=TriggerKind.CRON, id="trg-1")


def test_trigger_cron_valid():
    t = Trigger(kind=TriggerKind.CRON, id="trg-1", cron_expr="0 9 * * 1")
    assert t.cron_expr == "0 9 * * 1"


def test_trigger_webhook_requires_path():
    with pytest.raises(ValidationError):
        Trigger(kind=TriggerKind.WEBHOOK, id="trg-1")


def test_trigger_event_requires_topic():
    with pytest.raises(ValidationError):
        Trigger(kind=TriggerKind.EVENT, id="trg-1")


def test_node_id_must_be_slug():
    with pytest.raises(ValidationError):
        Node(id="BadID", kind=NodeKind.LLM_CALL, name="X")


def test_node_config_extra_forbidden():
    with pytest.raises(ValidationError):
        NodeConfig(unknown_key="x")


def test_workflow_requires_at_least_one_node():
    with pytest.raises(ValidationError):
        Workflow(
            id="wf-1",
            name="X",
            trigger=Trigger(kind=TriggerKind.MANUAL, id="trg-1"),
            nodes=[],
            edges=[],
        )


def test_workflow_edge_referencing_unknown_node_rejected():
    with pytest.raises(ValidationError):
        Workflow(
            **_wf_kwargs(
                edges=[Edge(source="n1", target="ghost")],
            )
        )


def test_workflow_duplicate_node_ids_rejected():
    with pytest.raises(ValidationError):
        Workflow(
            **_wf_kwargs(
                nodes=[
                    Node(id="dup", kind=NodeKind.LLM_CALL, name="A"),
                    Node(id="dup", kind=NodeKind.OUTPUT, name="B"),
                ],
                edges=[],
            )
        )


def test_workflow_cycle_rejected():
    with pytest.raises(ValidationError):
        Workflow(
            **_wf_kwargs(
                nodes=[
                    Node(id="a", kind=NodeKind.LLM_CALL, name="A"),
                    Node(id="b", kind=NodeKind.LLM_CALL, name="B"),
                ],
                edges=[
                    Edge(source="a", target="b"),
                    Edge(source="b", target="a"),
                ],
            )
        )


def test_workflow_dag_accepted():
    wf = Workflow(**_wf_kwargs())
    assert wf.id == "wf-1" and len(wf.edges) == 1


def test_variable_secret_requires_secret_ref():
    with pytest.raises(ValidationError):
        Variable(name="db_pw", scope=VariableScope.SECRET)


def test_variable_secret_with_ref_ok():
    v = Variable(name="db_pw", scope=VariableScope.SECRET, secret_ref="vault:db_pw")
    assert v.secret_ref == "vault:db_pw"


def test_build_simple_chain_links_nodes():
    trig = Trigger(kind=TriggerKind.MANUAL, id="trg-1")
    nodes = [
        Node(id="step-a", kind=NodeKind.LLM_CALL, name="A"),
        Node(id="step-b", kind=NodeKind.LLM_CALL, name="B"),
        Node(id="step-c", kind=NodeKind.OUTPUT, name="C"),
    ]
    tmpl = build_simple_chain("demo", "Demo EN", "Demo TR", "Demo ES", trig, nodes)
    edges = tmpl.workflow.edges
    assert [(e.source, e.target) for e in edges] == [
        ("step-a", "step-b"),
        ("step-b", "step-c"),
    ]
    assert all(e.kind == EdgeKind.SUCCESS for e in edges)


def test_template_count_50():
    assert len(TEMPLATES) == 50


def test_template_ids_are_unique_slugs():
    ids = [t.id for t in list_templates()]
    assert len(ids) == len(set(ids))


def test_template_each_has_translations():
    for t in list_templates():
        assert t.title_en and t.title_tr and t.title_es


def test_template_each_workflow_valid():
    for t in list_templates():
        assert isinstance(t.workflow, Workflow)
        assert len(t.workflow.nodes) >= 1
        for e in t.workflow.edges:
            assert e.source in {n.id for n in t.workflow.nodes}
            assert e.target in {n.id for n in t.workflow.nodes}


def test_get_template_unknown_raises():
    with pytest.raises(KeyError):
        get_template("does-not-exist")


def test_email_classify_draft_template_shape():
    t = get_template("email-classify-draft")
    kinds = [n.kind for n in t.workflow.nodes]
    assert NodeKind.HITL in kinds
    assert NodeKind.ABS_TOOL in kinds


def test_template_returns_workflow_template_type():
    t = list_templates()[0]
    assert isinstance(t, WorkflowTemplate)
