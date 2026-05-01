"""2-stage workflow validator (Sprint 19 T-S03.3).

Stage 1: schema_check — rely on Pydantic by attempting `Workflow.model_validate`.
Stage 2: semantic_check — extra checks Pydantic can't enforce:
  - no infinite loops (cycle detection lives in ontology, but verified here too)
  - tenant boundary respected on every cerbos_check / cross-tenant secret
  - destructive ops require an explicit HITL approval node before execution
  - reachability: every node is reachable from the trigger entry node

Returns `ValidationReport` aggregating Stage 1 + Stage 2 findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from .ontology import EdgeKind, NodeKind, Workflow

_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {
        "abs.gmail_send",
        "abs.linear_create_ticket",
        "abs.rag_ingest",
        "abs.notion_log",
    }
)
_DESTRUCTIVE_HTTP_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def schema_check(payload: dict[str, Any]) -> tuple[Workflow | None, list[str]]:
    """Stage 1 — Pydantic validation."""
    try:
        wf = Workflow.model_validate(payload)
        return wf, []
    except ValidationError as exc:
        return None, [str(err) for err in exc.errors()]


def semantic_check(wf: Workflow) -> tuple[list[str], list[str]]:
    """Stage 2 — semantic invariants. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    by_id = {n.id: n for n in wf.nodes}

    # 1. Reachability from the assumed entry node (first node in nodes[]).
    if wf.nodes:
        entry = wf.nodes[0].id
        adjacency: dict[str, list[str]] = {nid: [] for nid in by_id}
        for e in wf.edges:
            adjacency[e.source].append(e.target)
        seen: set[str] = set()
        stack = [entry]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adjacency.get(cur, []))
        unreachable = set(by_id) - seen
        if unreachable:
            errors.append(
                f"unreachable nodes from entry {entry!r}: {sorted(unreachable)}"
            )

    # 2. Tenant boundary on cerbos_check usage.
    if wf.tenant_scoped:
        cerbos_present = any(
            n.kind == NodeKind.ABS_TOOL and (n.config.tool_name or "").endswith("cerbos_check")
            for n in wf.nodes
        )
        rag_or_send = any(
            n.kind == NodeKind.ABS_TOOL
            and (n.config.tool_name or "")
            in {"abs.rag_query", "abs.rag_ingest", "abs.gmail_send"}
            for n in wf.nodes
        )
        if rag_or_send and not cerbos_present:
            warnings.append(
                "tenant-scoped workflow uses RAG/email send without an abs.cerbos_check gate; "
                "consider adding one before the destructive call"
            )

    # 3. Destructive ops require a preceding HITL approval node.
    incoming: dict[str, list[str]] = {nid: [] for nid in by_id}
    for e in wf.edges:
        incoming[e.target].append(e.source)
    hitl_ids = {n.id for n in wf.nodes if n.kind == NodeKind.HITL}

    for node in wf.nodes:
        is_destructive = False
        if node.kind == NodeKind.ABS_TOOL and (node.config.tool_name or "") in _DESTRUCTIVE_TOOLS:
            is_destructive = True
        if node.kind == NodeKind.API_REQUEST and (node.config.method or "GET").upper() in _DESTRUCTIVE_HTTP_METHODS:
            is_destructive = True
        if not is_destructive:
            continue
        if not _has_hitl_ancestor(node.id, incoming, hitl_ids):
            errors.append(
                f"destructive node {node.id!r} ({node.kind.value}) requires a HITL approval ancestor"
            )

    # 4. Defence-in-depth: cycle detection (ontology already rejects, but
    # we belt-and-braces in case payload bypassed Pydantic).
    if _has_cycle(wf):
        errors.append("workflow has a cycle")

    return errors, warnings


def _has_hitl_ancestor(
    node_id: str,
    incoming: dict[str, list[str]],
    hitl_ids: set[str],
) -> bool:
    seen: set[str] = set()
    stack = list(incoming.get(node_id, []))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        if cur in hitl_ids:
            return True
        stack.extend(incoming.get(cur, []))
    return False


def _has_cycle(wf: Workflow) -> bool:
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n.id: WHITE for n in wf.nodes}
    successors: dict[str, list[str]] = {n.id: [] for n in wf.nodes}
    for e in wf.edges:
        if e.source in successors:
            successors[e.source].append(e.target)

    def visit(nid: str) -> bool:
        if color[nid] == GRAY:
            return True
        if color[nid] == BLACK:
            return False
        color[nid] = GRAY
        for nxt in successors.get(nid, []):
            if nxt in color and visit(nxt):
                return True
        color[nid] = BLACK
        return False

    return any(visit(nid) for nid in color if color[nid] == WHITE)


def validate_workflow(payload: dict[str, Any]) -> ValidationReport:
    """Run both stages. ok=True only when Stage 1 + Stage 2 produce zero errors."""
    wf, schema_errors = schema_check(payload)
    if wf is None:
        return ValidationReport(ok=False, errors=schema_errors)
    sem_errors, sem_warnings = semantic_check(wf)
    return ValidationReport(
        ok=not sem_errors,
        errors=sem_errors,
        warnings=sem_warnings,
    )


__all__ = [
    "EdgeKind",
    "ValidationReport",
    "schema_check",
    "semantic_check",
    "validate_workflow",
]
