# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Pydantic ontology for the ABS NL-driven workflow builder."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class TriggerKind(str, Enum):
    WEBHOOK = "webhook"
    CRON = "cron"
    EVENT = "event"
    MANUAL = "manual"


class NodeKind(str, Enum):
    LLM_CALL = "llm_call"
    API_REQUEST = "api_request"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    HITL = "hitl"
    ABS_TOOL = "abs_tool"
    TRANSFORM = "transform"
    OUTPUT = "output"


class EdgeKind(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    CONDITIONAL = "conditional"


class VariableScope(str, Enum):
    WORKFLOW = "workflow"
    NODE = "node"
    SECRET = "secret"


_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_VAR_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CRON_RE = re.compile(r"^(\S+\s){4}\S+$")


class Trigger(BaseModel):
    kind: TriggerKind
    id: str
    cron_expr: Optional[str] = None
    webhook_path: Optional[str] = None
    event_topic: Optional[str] = None
    description: str = Field(default="", max_length=240)

    @field_validator("id")
    @classmethod
    def _id_slug(cls, v: str) -> str:
        if not _SLUG_RE.fullmatch(v):
            raise ValueError("trigger.id must be slug")
        return v

    @field_validator("cron_expr")
    @classmethod
    def _cron(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _CRON_RE.fullmatch(v):
            raise ValueError("cron_expr must be 5-field cron")
        return v

    @model_validator(mode="after")
    def _kind_consistency(self) -> "Trigger":
        if self.kind == TriggerKind.CRON and not self.cron_expr:
            raise ValueError("cron trigger requires cron_expr")
        if self.kind == TriggerKind.WEBHOOK and not self.webhook_path:
            raise ValueError("webhook trigger requires webhook_path")
        if self.kind == TriggerKind.EVENT and not self.event_topic:
            raise ValueError("event trigger requires event_topic")
        return self


class NodeConfig(BaseModel):
    model_config = {"extra": "forbid"}

    model: Optional[str] = None
    prompt: Optional[str] = None
    method: Optional[str] = None
    url: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    condition_expr: Optional[str] = None
    approval_role: Optional[str] = None
    script: Optional[str] = None
    output_template: Optional[str] = None


class Node(BaseModel):
    id: str
    kind: NodeKind
    name: str = Field(..., max_length=120)
    config: NodeConfig = Field(default_factory=NodeConfig)
    retry_max: int = Field(default=0, ge=0, le=5)
    timeout_s: int = Field(default=60, ge=1, le=900)

    @field_validator("id")
    @classmethod
    def _id_slug(cls, v: str) -> str:
        if not _SLUG_RE.fullmatch(v):
            raise ValueError("node.id must be slug")
        return v


class Edge(BaseModel):
    source: str
    target: str
    kind: EdgeKind = EdgeKind.SUCCESS
    condition: Optional[str] = None


class Variable(BaseModel):
    name: str
    scope: VariableScope
    default: Any = None
    secret_ref: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name_pattern(cls, v: str) -> str:
        if not _VAR_RE.fullmatch(v):
            raise ValueError("variable name must match pattern")
        return v

    @model_validator(mode="after")
    def _secret_consistency(self) -> "Variable":
        if self.scope == VariableScope.SECRET and not self.secret_ref:
            raise ValueError("secret-scoped variable requires secret_ref")
        return self


def _detect_cycle(node_ids: list[str], edges: list[Edge]) -> Optional[list[str]]:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_ids}
    successors: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for e in edges:
        if e.source in successors:
            successors[e.source].append(e.target)

    def visit(nid: str, path: list[str]) -> Optional[list[str]]:
        if color[nid] == GRAY:
            idx = path.index(nid)
            return path[idx:] + [nid]
        if color[nid] == BLACK:
            return None
        color[nid] = GRAY
        path.append(nid)
        for nxt in successors.get(nid, []):
            if nxt not in color:
                continue
            res = visit(nxt, path)
            if res is not None:
                return res
        path.pop()
        color[nid] = BLACK
        return None

    for nid in node_ids:
        if color[nid] == WHITE:
            cycle = visit(nid, [])
            if cycle is not None:
                return cycle
    return None


class Workflow(BaseModel):
    id: str
    name: str
    description: str = Field(default="", max_length=500)
    locale: str = "en"
    tenant_scoped: bool = True
    trigger: Trigger
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    variables: list[Variable] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_slug(cls, v: str) -> str:
        if not _SLUG_RE.fullmatch(v):
            raise ValueError("workflow.id must be slug")
        return v

    @model_validator(mode="after")
    def _validate_graph(self) -> "Workflow":
        if not self.nodes:
            raise ValueError("workflow must have at least one node")
        node_ids = [n.id for n in self.nodes]
        node_id_set = set(node_ids)
        if len(node_id_set) != len(node_ids):
            raise ValueError("workflow has duplicate node ids")
        for e in self.edges:
            if e.source not in node_id_set:
                raise ValueError(f"edge.source {e.source!r} is not a known node")
            if e.target not in node_id_set:
                raise ValueError(f"edge.target {e.target!r} is not a known node")
        cycle = _detect_cycle(node_ids, self.edges)
        if cycle:
            raise ValueError(f"workflow has a cycle: {' -> '.join(cycle)}")
        return self


class WorkflowTemplate(BaseModel):
    id: str
    title_en: str
    title_tr: str
    title_es: str
    workflow: Workflow
    tags: list[str] = Field(default_factory=list)


def build_simple_chain(
    template_id: str,
    title_en: str,
    title_tr: str,
    title_es: str,
    trigger: Trigger,
    nodes: list[Node],
    variables: Optional[list[Variable]] = None,
    tags: Optional[list[str]] = None,
) -> WorkflowTemplate:
    """Wire nodes into a linear SUCCESS chain and wrap as a localised template."""
    edges: list[Edge] = []
    for a, b in zip(nodes, nodes[1:]):
        edges.append(Edge(source=a.id, target=b.id, kind=EdgeKind.SUCCESS))
    workflow = Workflow(
        id=template_id,
        name=title_en,
        description=title_en[:500],
        locale="en",
        trigger=trigger,
        nodes=list(nodes),
        edges=edges,
        variables=variables or [],
        tags=tags or [],
    )
    return WorkflowTemplate(
        id=template_id,
        title_en=title_en,
        title_tr=title_tr,
        title_es=title_es,
        workflow=workflow,
        tags=tags or [],
    )


__all__ = [
    "Edge",
    "EdgeKind",
    "Node",
    "NodeConfig",
    "NodeKind",
    "Trigger",
    "TriggerKind",
    "Variable",
    "VariableScope",
    "Workflow",
    "WorkflowTemplate",
    "build_simple_chain",
]
