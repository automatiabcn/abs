# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Agentic workflow runner — execute an ordered agent chain. Tenant-scoped."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlmodel import Session, select

from app.agents.registry import AGENTS, agents_by_category
from app.agents.runtime import run_agent
from app.db.growth_models import AgenticWorkflowDef, WorkflowRun
from app.db.session import get_engine

logger = logging.getLogger(__name__)

NODE_KINDS = ["trigger", "agent", "retrieval", "connector",
              "policy", "approval", "action", "branch", "sub_workflow"]


def palette() -> Dict[str, Any]:
    """Node palette for the designer: agents (by category) + node kinds."""
    grouped = agents_by_category()
    return {
        "agents": {
            cat: [{"id": a.id, "name": a.name, "risk": a.risk} for a in items]
            for cat, items in grouped.items()
        },
        "node_kinds": NODE_KINDS,
    }


# ── Workflow graph definition (Stage D — interactive editor) ──────────────────
def _default_graph() -> Dict[str, Any]:
    """Canonical 'Inbound → Cevap Taslağı' graph — mirrors the mockup-03 layout
    so a tenant with no saved definition still opens a meaningful flow."""
    return {
        "name": "Inbound → Cevap Taslağı",
        "nodes": [
            {"id": "trigger", "kind": "trigger", "name": "Inbound talep", "desc": "form · email · WhatsApp", "x": 20, "y": 160, "agent_id": None},
            {"id": "triage", "kind": "agent", "name": "Triage", "desc": "intent sınıflandırma", "x": 250, "y": 160, "agent_id": "inbound_triage"},
            {"id": "retrieval", "kind": "retrieval", "name": "RAG + Graph", "desc": "hybrid · cite", "x": 480, "y": 60, "agent_id": None},
            {"id": "policy", "kind": "policy", "name": "Policy Engine", "desc": "Cerbos · risk", "x": 480, "y": 280, "agent_id": None},
            {"id": "knowledge", "kind": "agent", "name": "Knowledge", "desc": "kaynak-gösteren taslak", "x": 710, "y": 60, "agent_id": "knowledge_base"},
            {"id": "consent", "kind": "policy", "name": "Consent Ledger", "desc": "kanal izni", "x": 710, "y": 280, "agent_id": None},
            {"id": "approval", "kind": "approval", "name": "Approval Gate", "desc": "orta-risk → onay", "x": 940, "y": 60, "agent_id": None},
            {"id": "action", "kind": "action", "name": "CRM Note + Route", "desc": "yönlendir", "x": 940, "y": 280, "agent_id": None},
        ],
        "edges": [
            {"source": "trigger", "target": "triage"},
            {"source": "triage", "target": "retrieval"},
            {"source": "triage", "target": "policy"},
            {"source": "retrieval", "target": "knowledge"},
            {"source": "policy", "target": "consent"},
            {"source": "knowledge", "target": "approval"},
            {"source": "consent", "target": "action"},
        ],
    }


def get_definition(*, tenant_slug: str, key: str = "default") -> Dict[str, Any]:
    """Saved graph for (tenant, key), or the default seed graph if none yet."""
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        row = db.exec(
            select(AgenticWorkflowDef).where(
                AgenticWorkflowDef.tenant_slug == tenant_slug,
                AgenticWorkflowDef.key == key,
            )
        ).first()
    if row is None:
        g = _default_graph()
        return {"key": key, "name": g["name"], "graph": g, "saved": False,
                "ordered_steps": ordered_agent_steps(g)}
    try:
        graph = json.loads(row.graph_json or "{}")
    except Exception:
        graph = _default_graph()
    return {"key": row.key, "name": row.name, "graph": graph, "saved": True,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "ordered_steps": ordered_agent_steps(graph)}


def save_definition(
    *, tenant_slug: str, key: str, name: str, graph: Dict[str, Any]
) -> Dict[str, Any]:
    """Persist the designer graph (nodes + positions + edges)."""
    tenant_slug = (tenant_slug or "default").strip()
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    clean = {"name": name, "nodes": nodes, "edges": edges}
    with Session(get_engine()) as db:
        row = db.exec(
            select(AgenticWorkflowDef).where(
                AgenticWorkflowDef.tenant_slug == tenant_slug,
                AgenticWorkflowDef.key == key,
            )
        ).first()
        if row is None:
            row = AgenticWorkflowDef(tenant_slug=tenant_slug, key=key)
        row.name = (name or "")[:200]
        row.graph_json = json.dumps(clean)[:65000]
        row.updated_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
        db.refresh(row)
    return {"key": key, "name": row.name, "saved": True,
            "node_count": len(nodes), "edge_count": len(edges),
            "ordered_steps": ordered_agent_steps(clean)}


def ordered_agent_steps(graph: Dict[str, Any]) -> List[str]:
    """Topological order of the graph's agent nodes → agent_id run sequence.

    Kahn's algorithm over all nodes (stable to insertion order on ties), then
    keep only agent-kind nodes that resolve to a known agent_id. Cyclic or
    malformed graphs fall back to node insertion order so a run is still possible.
    """
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    by_id = {n.get("id"): n for n in nodes if n.get("id")}
    indeg = {nid: 0 for nid in by_id}
    adj: Dict[str, List[str]] = {nid: [] for nid in by_id}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in by_id and t in by_id:
            adj[s].append(t)
            indeg[t] += 1

    order: List[str] = []
    queue = [nid for nid in by_id if indeg[nid] == 0]
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for nxt in adj[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(by_id):           # cycle → fall back to insertion order
        order = list(by_id.keys())

    steps: List[str] = []
    for nid in order:
        n = by_id[nid]
        if n.get("kind") == "agent":
            aid = n.get("agent_id")
            if aid in AGENTS:
                steps.append(aid)
    return steps


async def run_workflow(
    *, tenant_slug: str, name: str, steps: List[str], input_text: str,
    trigger: str = "manual", actor: str = "",
) -> Dict[str, Any]:
    """Run an ordered chain of agent steps; risky steps open approvals.

    Each step receives the original input plus the previous step's summary, so
    context threads down the chain (multi-agent coordination). Unknown agent ids
    are skipped (recorded). Always returns a persisted run."""
    tenant_slug = (tenant_slug or "default").strip()
    t0 = time.perf_counter()
    results: List[dict] = []
    approvals_opened = 0
    prev_summary = ""
    status = "done"

    for agent_id in steps:
        if agent_id not in AGENTS:
            results.append({"agent_id": agent_id, "skipped": "unknown_agent"})
            status = "partial"
            continue
        task = input_text if not prev_summary else (
            f"{input_text}\n\nÖnceki adım ({results[-1].get('agent_id','')}) çıktısı: "
            f"{prev_summary}"
        )
        try:
            res = await run_agent(
                agent_id, task, tenant_id=tenant_slug, user_subject=actor
            )
        except Exception as exc:  # noqa: BLE001 — one bad step → partial, continue
            logger.info("workflow step %s failed: %s", agent_id, exc)
            results.append({"agent_id": agent_id, "error": str(exc)[:200]})
            status = "partial"
            continue
        prev_summary = res.summary
        step = {
            "agent_id": agent_id, "summary": res.summary,
            "confidence": res.confidence, "risk": res.risk,
            "requires_approval": res.requires_approval,
        }
        # persist run + (risky) approval via the approvals service
        try:
            from app.approvals import create_approval_from_result, log_agent_run

            run_id = log_agent_run(res, tenant_slug=tenant_slug, actor=actor, task=task)
            step["run_id"] = run_id
            if res.requires_approval:
                ap = create_approval_from_result(
                    res, tenant_slug=tenant_slug, requester=actor, agent_run_id=run_id
                )
                step["approval_id"] = ap["id"]
                approvals_opened += 1
        except Exception:  # noqa: BLE001 — persistence best-effort
            logger.info("workflow step persistence skipped", exc_info=True)
        results.append(step)

    elapsed = int((time.perf_counter() - t0) * 1000)
    row = WorkflowRun(
        tenant_slug=tenant_slug, name=name[:200], trigger=trigger[:32],
        steps_json=json.dumps(steps)[:65000],
        result_json=json.dumps(results)[:65000],
        status=status, step_count=len(steps), approvals_opened=approvals_opened,
        elapsed_ms=elapsed, actor=actor,
    )
    with Session(get_engine()) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        rid = int(row.id)
    return {
        "id": rid, "name": name, "status": status, "trigger": trigger,
        "step_count": len(steps), "steps_run": len([r for r in results if "summary" in r]),
        "approvals_opened": approvals_opened, "elapsed_ms": elapsed,
        "results": results,
    }


def list_runs(*, tenant_slug: str, limit: int = 30) -> Dict[str, Any]:
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        rows = list(
            db.exec(select(WorkflowRun).where(WorkflowRun.tenant_slug == tenant_slug)
                    .order_by(WorkflowRun.created_at.desc()).limit(limit))
        )
    return {
        "runs": [
            {
                "id": r.id, "name": r.name, "trigger": r.trigger,
                "status": r.status, "step_count": r.step_count,
                "approvals_opened": r.approvals_opened, "elapsed_ms": r.elapsed_ms,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }
