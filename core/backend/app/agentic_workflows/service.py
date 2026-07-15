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

NODE_KINDS = [
    "trigger",
    "agent",
    "custom_ai",
    "retrieval",
    "connector",
    "policy",
    "consent",
    "approval",
    "action",
    "branch",
    "sub_workflow",
]


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
    """Canonical 'Inbound → Reply Draft' graph, so a tenant with no saved
    definition still opens a meaningful flow instead of a blank canvas."""
    return {
        "name": "Inbound → Reply Draft",
        "nodes": [
            {
                "id": "trigger",
                "kind": "trigger",
                "name": "Inbound request",
                "desc": "form · email · WhatsApp",
                "x": 20,
                "y": 160,
                "agent_id": None,
            },
            {
                "id": "triage",
                "kind": "agent",
                "name": "Triage",
                "desc": "intent classification",
                "x": 250,
                "y": 160,
                "agent_id": "inbound_triage",
            },
            {
                "id": "retrieval",
                "kind": "retrieval",
                "name": "RAG + Graph",
                "desc": "hybrid · cite",
                "x": 480,
                "y": 60,
                "agent_id": None,
            },
            {
                "id": "policy",
                "kind": "policy",
                "name": "Policy Engine",
                "desc": "Cerbos · risk",
                "x": 480,
                "y": 280,
                "agent_id": None,
            },
            {
                "id": "knowledge",
                "kind": "agent",
                "name": "Knowledge",
                "desc": "cited draft",
                "x": 710,
                "y": 60,
                "agent_id": "knowledge_base",
            },
            {
                "id": "consent",
                "kind": "policy",
                "name": "Consent Ledger",
                "desc": "channel consent",
                "x": 710,
                "y": 280,
                "agent_id": None,
            },
            {
                "id": "approval",
                "kind": "approval",
                "name": "Approval Gate",
                "desc": "medium risk → approval",
                "x": 940,
                "y": 60,
                "agent_id": None,
            },
            {
                "id": "action",
                "kind": "action",
                "name": "CRM Note + Route",
                "desc": "route",
                "x": 940,
                "y": 280,
                "agent_id": None,
            },
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
        return {
            "key": key,
            "name": g["name"],
            "graph": g,
            "saved": False,
            "ordered_steps": ordered_agent_steps(g),
        }
    try:
        graph = json.loads(row.graph_json or "{}")
    except Exception:
        graph = _default_graph()
    return {
        "key": row.key,
        "name": row.name,
        "graph": graph,
        "saved": True,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "ordered_steps": ordered_agent_steps(graph),
    }


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
    return {
        "key": key,
        "name": row.name,
        "saved": True,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "ordered_steps": ordered_agent_steps(clean),
    }


def _topo_order(graph: Dict[str, Any]):
    """Kahn topological sort over a designer graph.

    Returns ``(order, by_id, wired)``: the ordered node ids (insertion-order
    stable on ties; a cycle falls back to insertion order so a run is still
    possible), the id→node map, and the set of nodes that touch ≥1 edge.
    """
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    by_id = {n.get("id"): n for n in nodes if n.get("id")}
    indeg = {nid: 0 for nid in by_id}
    adj: Dict[str, List[str]] = {nid: [] for nid in by_id}
    wired: set[str] = set()  # nodes that touch ≥1 edge
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in by_id and t in by_id:
            adj[s].append(t)
            indeg[t] += 1
            wired.add(s)
            wired.add(t)

    order: List[str] = []
    queue = [nid for nid in by_id if indeg[nid] == 0]
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for nxt in adj[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(by_id):  # cycle → fall back to insertion order
        order = list(by_id.keys())
    return order, by_id, wired


def ordered_agent_steps(graph: Dict[str, Any]) -> List[str]:
    """Topological order of the graph's agent nodes → agent_id run sequence.

    Only WIRED agent nodes that resolve to a known agent_id run — a node dropped
    on the canvas but not yet connected is not part of the flow.
    """
    order, by_id, wired = _topo_order(graph)
    steps: List[str] = []
    for nid in order:
        n = by_id[nid]
        if n.get("kind") == "agent" and nid in wired and n.get("agent_id") in AGENTS:
            steps.append(n["agent_id"])
    return steps


_RISK_RANK = {"low": 0, "medium": 1, "high": 2}


_MAX_SUBWORKFLOW_DEPTH = 3


async def run_workflow_graph(
    *,
    tenant_slug: str,
    name: str,
    graph: Dict[str, Any],
    input_text: str,
    trigger: str = "manual",
    actor: str = "",
    dry_run: bool = False,
    _depth: int = 0,
) -> Dict[str, Any]:
    """Execute the FULL designer graph — every wired node runs in topological
    order, dispatched by kind (not only agent nodes):

      agent      → Agent Runtime call (threads the prior summary + retrieved
                   context); risky results open Approval Center items.
      retrieval  → hybrid RAG query; snippets thread into the next agent's prompt.
      policy     → risk checkpoint over the accumulated step risk.
      consent    → channel-consent checkpoint.
      approval   → human-approval gate marker.
      action     → outbound action marker (CRM note / route).
      trigger / branch / sub_workflow / connector → structural, recorded.

    ``step_count`` counts every executed (non-trigger) node, so a run mirrors the
    pipeline drawn on the canvas instead of only its agent nodes. ``dry_run``
    still runs agents + retrieval for a preview but persists nothing and opens
    no approvals.
    """
    tenant_slug = (tenant_slug or "default").strip()
    t0 = time.perf_counter()
    order, by_id, wired = _topo_order(graph)
    multi = len(by_id) > 1
    # edge maps for branch routing: a branch node prunes the downstream of the
    # edges it does NOT select; a node stays alive if any incoming edge comes
    # from a non-pruned source (so a merge after the taken branch survives).
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    out_edges: Dict[str, List[dict]] = {}
    in_sources: Dict[str, List[str]] = {}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in by_id and t in by_id:
            out_edges.setdefault(s, []).append(e)
            in_sources.setdefault(t, []).append(s)
    pruned: set[str] = set()  # nodes a branch routed away from
    dead_edges: set[tuple] = set()  # (source,target) edges that won't fire
    node_outputs: Dict[str, dict] = {}

    def _is_reachable(t: str) -> bool:
        """A node with incoming edges runs only if at least one of them FIRES:
        its source is not pruned and the edge is not a non-selected branch edge.
        Root nodes (no incoming edge) always run. Processed in topo order, so a
        branch upstream has already marked its dead edges by the time we get
        here — this also handles merges (alive if the taken branch reaches it)."""
        srcs = in_sources.get(t, [])
        if not srcs:
            return True
        return any(s not in pruned and (s, t) not in dead_edges for s in srcs)

    results: List[dict] = []
    approvals_opened = 0
    would_open = 0
    prev_summary = ""
    context_snippets: List[str] = []
    risk_seen = "low"
    status = "done"
    executed = 0

    for nid in order:
        if multi and nid not in wired:
            continue  # unconnected node is not part of the flow
        if not _is_reachable(nid):
            # no incoming edge fires → an upstream branch routed away from here
            pruned.add(nid)
            results.append(
                {
                    "kind": by_id[nid].get("kind"),
                    "name": by_id[nid].get("name") or nid,
                    "status": "skipped",
                    "note": "branch not taken",
                }
            )
            continue
        n = by_id[nid]
        kind = n.get("kind")
        nm = n.get("name") or kind or "node"
        cfg = n.get("config") if isinstance(n.get("config"), dict) else {}

        if kind == "trigger":
            results.append({"kind": kind, "name": nm, "status": "started"})
            continue

        if kind == "agent":
            agent_id = n.get("agent_id")
            if agent_id not in AGENTS:
                results.append({"kind": kind, "name": nm, "skipped": "unknown_agent"})
                status = "partial"
                continue
            task = (
                input_text
                if not prev_summary
                else (f"{input_text}\n\nOutput of the previous step: {prev_summary}")
            )
            if context_snippets:
                task += "\n\nRelevant context:\n- " + "\n- ".join(context_snippets[:5])
            try:
                res = await run_agent(
                    agent_id, task, tenant_id=tenant_slug, user_subject=actor
                )
            except Exception as exc:  # noqa: BLE001 — one bad step → partial, continue
                logger.info("workflow agent %s failed: %s", agent_id, exc)
                results.append(
                    {
                        "kind": kind,
                        "name": nm,
                        "agent_id": agent_id,
                        "error": str(exc)[:200],
                    }
                )
                status = "partial"
                continue
            prev_summary = res.summary
            node_outputs[nid] = {"text": res.summary, "risk": res.risk}
            if _RISK_RANK.get(res.risk, 0) > _RISK_RANK.get(risk_seen, 0):
                risk_seen = res.risk
            step = {
                "kind": kind,
                "name": nm,
                "agent_id": agent_id,
                "summary": res.summary,
                "confidence": res.confidence,
                "risk": res.risk,
                "requires_approval": res.requires_approval,
            }
            executed += 1
            if dry_run:
                if res.requires_approval:
                    would_open += 1
                step["would_open_approval"] = res.requires_approval
                results.append(step)
                continue
            try:
                from app.approvals import create_approval_from_result, log_agent_run

                run_id = log_agent_run(
                    res, tenant_slug=tenant_slug, actor=actor, task=task
                )
                step["run_id"] = run_id
                if res.requires_approval:
                    ap = create_approval_from_result(
                        res,
                        tenant_slug=tenant_slug,
                        requester=actor,
                        agent_run_id=run_id,
                    )
                    step["approval_id"] = ap["id"]
                    approvals_opened += 1
            except Exception:  # noqa: BLE001 — persistence best-effort
                logger.info("workflow step persistence skipped", exc_info=True)
            results.append(step)
            continue

        if kind == "custom_ai":
            # Free-form AI step: the operator describes (in natural language) what
            # this node should do; it runs on the provider cascade with the prior
            # summary + retrieved context threaded in. No code sandbox — safer and
            # native to an AI-orchestration product.
            instruction = (cfg.get("instruction") or n.get("desc") or nm).strip()
            ctx = (
                f"\n\nOutput of the previous step: {prev_summary}"
                if prev_summary
                else ""
            )
            if context_snippets:
                ctx += "\n\nRelevant context:\n- " + "\n- ".join(context_snippets[:5])
            prompt = f"{instruction}{ctx}"
            try:
                from app.cascade.orchestrator import call_with_cascade
                from app.providers.cascade import PROVIDER_ORDER_DEFAULT

                order_p = list(PROVIDER_ORDER_DEFAULT)
                resp = await call_with_cascade(
                    prompt[:8000],
                    primary=order_p[0],
                    fallbacks=tuple(order_p[1:]),
                    tenant_id=tenant_slug,
                    user_subject=actor,
                )
                out_text = (getattr(resp, "text", "") or "").strip()
            except Exception as exc:  # noqa: BLE001 — provider failure → partial, continue
                logger.info("workflow custom_ai step failed: %s", exc)
                results.append({"kind": kind, "name": nm, "error": str(exc)[:200]})
                status = "partial"
                continue
            prev_summary = out_text or prev_summary
            node_outputs[nid] = {"text": out_text}
            results.append(
                {
                    "kind": kind,
                    "name": nm,
                    "status": "done",
                    "summary": out_text[:600],
                    "provider": getattr(resp, "provider", ""),
                    "model": getattr(resp, "model", ""),
                }
            )
            executed += 1
            continue

        if kind == "retrieval":
            top_k = cfg.get("top_k") if isinstance(cfg.get("top_k"), int) else 5
            query_text = (cfg.get("query") or "").strip() or prev_summary or input_text
            scope = (cfg.get("scope_company") or "").strip()
            if scope:
                # Focus on one company: prefixing the firm name steers both the
                # cosine pull and the BM25 re-rank toward that company's context.
                query_text = f"{scope}: {query_text}".strip()
            try:
                from app.rag.hybrid import query_hybrid

                hits = await query_hybrid(query_text, top_k=max(1, min(top_k, 20)))
            except Exception as exc:  # noqa: BLE001 — retrieval failure → skip, continue
                results.append(
                    {
                        "kind": kind,
                        "name": nm,
                        "status": "skipped",
                        "error": str(exc)[:160],
                    }
                )
                executed += 1
                continue
            snippets = [
                (h.get("text") or h.get("document") or "")
                for h in hits
                if isinstance(h, dict) and not h.get("error")
            ]
            snippets = [s for s in snippets if s]
            context_snippets.extend(snippets[:5])
            results.append(
                {
                    "kind": kind,
                    "name": nm,
                    "status": "done",
                    "retrieved": len(snippets),
                    "scope": scope or None,
                }
            )
            executed += 1
            continue

        if kind == "policy":
            threshold = (cfg.get("risk_threshold") or "high").strip()
            block = _RISK_RANK.get(risk_seen, 0) >= _RISK_RANK.get(threshold, 2)
            results.append(
                {
                    "kind": kind,
                    "name": nm,
                    "status": "done",
                    "decision": "review" if block else "allow",
                    "risk_seen": risk_seen,
                    "threshold": threshold,
                }
            )
            executed += 1
            continue

        if kind == "consent":
            channel = (cfg.get("channel") or "").strip()
            results.append(
                {
                    "kind": kind,
                    "name": nm,
                    "status": "done",
                    "channel": channel or "any",
                    "note": "channel-consent checkpoint",
                }
            )
            executed += 1
            continue

        if kind == "approval":
            role = (cfg.get("role") or "").strip()
            results.append(
                {
                    "kind": kind,
                    "name": nm,
                    "status": "gate",
                    "role": role or "admin",
                    "note": "human-approval gate",
                }
            )
            executed += 1
            continue

        if kind == "connector":
            # Real execution: run the configured connector's adapter sync into
            # the growth tables (companies/contacts/leads). dry-run previews
            # without firing the side-effecting sync.
            connector_id = (
                cfg.get("connector_id") or cfg.get("connector") or ""
            ).strip()
            if not connector_id:
                results.append(
                    {
                        "kind": kind,
                        "name": nm,
                        "status": "skipped",
                        "note": "no connector_id configured",
                    }
                )
                status = "partial"
                executed += 1
                continue
            if dry_run:
                results.append(
                    {
                        "kind": kind,
                        "name": nm,
                        "status": "preview",
                        "connector_id": connector_id,
                        "note": "sync skipped in dry-run",
                    }
                )
                executed += 1
                continue
            try:
                from app.connectors.service import sync as connector_sync

                sres = await connector_sync(
                    tenant_slug=tenant_slug, connector_id=connector_id
                )
            except Exception as exc:  # noqa: BLE001 — one bad step → partial
                results.append(
                    {
                        "kind": kind,
                        "name": nm,
                        "status": "skipped",
                        "connector_id": connector_id,
                        "error": str(exc)[:160],
                    }
                )
                status = "partial"
                executed += 1
                continue
            ok = bool(sres.get("ok"))
            results.append(
                {
                    "kind": kind,
                    "name": nm,
                    "status": "done" if ok else "partial",
                    "connector_id": connector_id,
                    "synced": sres.get("total"),
                    "error": sres.get("error"),
                }
            )
            if not ok:
                status = "partial"
            executed += 1
            continue

        if kind == "action":
            action_type = (cfg.get("action_type") or "").strip()
            target = (cfg.get("target") or "").strip()
            results.append(
                {
                    "kind": kind,
                    "name": nm,
                    "status": "executed",
                    "action_type": action_type or "note",
                    "target": target,
                    "note": "outbound action",
                }
            )
            executed += 1
            continue

        if kind == "branch":
            # Conditional routing: evaluate the node's condition over upstream
            # outputs ({{node_id}} refs), then prune the downstream of the edges
            # that don't match. Outgoing edges carry when="true"/"false";
            # unlabelled edges always fire.
            expr = (cfg.get("condition_expr") or cfg.get("condition") or "").strip()
            try:
                from app.workflow_v10.condition_eval import ConditionError, evaluate

                decision = evaluate(expr, node_outputs) if expr else True
            except ConditionError as exc:
                results.append(
                    {
                        "kind": kind,
                        "name": nm,
                        "status": "error",
                        "error": f"bad condition: {exc}"[:160],
                    }
                )
                status = "partial"
                executed += 1
                continue
            want = "true" if decision else "false"
            for e in out_edges.get(nid, []):
                when = (e.get("when") or "").strip().lower()
                if when in ("true", "false") and when != want:
                    dead_edges.add((nid, e.get("target")))
            node_outputs[nid] = {"text": want}
            results.append(
                {
                    "kind": kind,
                    "name": nm,
                    "status": "done",
                    "decision": want,
                    "condition": expr or "(empty→true)",
                }
            )
            executed += 1
            continue

        if kind == "sub_workflow":
            # Run a saved workflow nested inside this one (depth-guarded so a
            # self/cyclic reference terminates).
            key = (cfg.get("workflow_key") or cfg.get("key") or "").strip()
            if not key:
                results.append(
                    {
                        "kind": kind,
                        "name": nm,
                        "status": "skipped",
                        "note": "no workflow_key configured",
                    }
                )
                status = "partial"
                executed += 1
                continue
            if _depth >= _MAX_SUBWORKFLOW_DEPTH:
                results.append(
                    {
                        "kind": kind,
                        "name": nm,
                        "status": "skipped",
                        "key": key,
                        "note": f"max sub-workflow depth {_MAX_SUBWORKFLOW_DEPTH}",
                    }
                )
                status = "partial"
                executed += 1
                continue
            sub_def = get_definition(tenant_slug=tenant_slug, key=key)
            if not sub_def.get("saved"):
                results.append(
                    {
                        "kind": kind,
                        "name": nm,
                        "status": "skipped",
                        "key": key,
                        "note": "workflow_key not found",
                    }
                )
                status = "partial"
                executed += 1
                continue
            try:
                sub = await run_workflow_graph(
                    tenant_slug=tenant_slug,
                    name=sub_def.get("name") or key,
                    graph=sub_def.get("graph") or {},
                    input_text=prev_summary or input_text,
                    trigger="sub_workflow",
                    actor=actor,
                    dry_run=dry_run,
                    _depth=_depth + 1,
                )
            except Exception as exc:  # noqa: BLE001 — one bad sub-run → partial
                results.append(
                    {
                        "kind": kind,
                        "name": nm,
                        "status": "skipped",
                        "key": key,
                        "error": str(exc)[:160],
                    }
                )
                status = "partial"
                executed += 1
                continue
            if sub.get("status") != "done":
                status = "partial"
            sub_sums = [
                r.get("summary") for r in sub.get("results", []) if r.get("summary")
            ]
            if sub_sums:
                prev_summary = sub_sums[-1]
                node_outputs[nid] = {"text": sub_sums[-1]}
            results.append(
                {
                    "kind": kind,
                    "name": nm,
                    "status": sub.get("status") or "done",
                    "key": key,
                    "sub_steps": sub.get("step_count", 0),
                }
            )
            executed += 1
            continue

        # unknown kind → honest skip (was a silent false green).
        results.append(
            {
                "kind": kind,
                "name": nm,
                "status": "skipped",
                "note": f"'{kind}' is not executed by the agentic engine yet",
            }
        )
        status = "partial"
        executed += 1

    elapsed = int((time.perf_counter() - t0) * 1000)
    steps_run = len(
        [r for r in results if "summary" in r or r.get("retrieved") is not None]
    )
    if dry_run:
        return {
            "id": None,
            "name": name,
            "status": status,
            "trigger": "dry-run",
            "dry_run": True,
            "step_count": executed,
            "steps_run": steps_run,
            "approvals_opened": 0,
            "would_open_approvals": would_open,
            "elapsed_ms": elapsed,
            "results": results,
        }
    run_ids = [nid for nid in order if not (multi and nid not in wired)]
    row = WorkflowRun(
        tenant_slug=tenant_slug,
        name=name[:200],
        trigger=trigger[:32],
        steps_json=json.dumps(run_ids)[:65000],
        result_json=json.dumps(results)[:65000],
        status=status,
        step_count=executed,
        approvals_opened=approvals_opened,
        elapsed_ms=elapsed,
        actor=actor,
    )
    with Session(get_engine()) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        rid = int(row.id)
    return {
        "id": rid,
        "name": name,
        "status": status,
        "trigger": trigger,
        "step_count": executed,
        "steps_run": steps_run,
        "approvals_opened": approvals_opened,
        "elapsed_ms": elapsed,
        "results": results,
    }


async def run_workflow(
    *,
    tenant_slug: str,
    name: str,
    steps: List[str],
    input_text: str,
    trigger: str = "manual",
    actor: str = "",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run an ordered chain of agent steps; risky steps open approvals.

    Each step receives the original input plus the previous step's summary, so
    context threads down the chain (multi-agent coordination). Unknown agent ids
    are skipped (recorded).

    ``dry_run`` is a side-effect-free preview: the agents still run (so you see
    what they'd produce) but NO agent runs are logged, NO approvals open and the
    run is not persisted — it only reports how many approvals *would* open."""
    tenant_slug = (tenant_slug or "default").strip()
    t0 = time.perf_counter()
    results: List[dict] = []
    approvals_opened = 0
    would_open = 0
    prev_summary = ""
    status = "done"

    for agent_id in steps:
        if agent_id not in AGENTS:
            results.append({"agent_id": agent_id, "skipped": "unknown_agent"})
            status = "partial"
            continue
        task = (
            input_text
            if not prev_summary
            else (
                f"{input_text}\n\nOutput of the previous step "
                f"({results[-1].get('agent_id', '')}): {prev_summary}"
            )
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
            "agent_id": agent_id,
            "summary": res.summary,
            "confidence": res.confidence,
            "risk": res.risk,
            "requires_approval": res.requires_approval,
        }
        if dry_run:
            # preview only: no agent-run log, no approval, just count what would open
            if res.requires_approval:
                would_open += 1
            step["would_open_approval"] = res.requires_approval
            results.append(step)
            continue
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
    if dry_run:
        # side-effect-free preview — nothing persisted
        return {
            "id": None,
            "name": name,
            "status": status,
            "trigger": "dry-run",
            "dry_run": True,
            "step_count": len(steps),
            "steps_run": len([r for r in results if "summary" in r]),
            "approvals_opened": 0,
            "would_open_approvals": would_open,
            "elapsed_ms": elapsed,
            "results": results,
        }
    row = WorkflowRun(
        tenant_slug=tenant_slug,
        name=name[:200],
        trigger=trigger[:32],
        steps_json=json.dumps(steps)[:65000],
        result_json=json.dumps(results)[:65000],
        status=status,
        step_count=len(steps),
        approvals_opened=approvals_opened,
        elapsed_ms=elapsed,
        actor=actor,
    )
    with Session(get_engine()) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        rid = int(row.id)
    return {
        "id": rid,
        "name": name,
        "status": status,
        "trigger": trigger,
        "step_count": len(steps),
        "steps_run": len([r for r in results if "summary" in r]),
        "approvals_opened": approvals_opened,
        "elapsed_ms": elapsed,
        "results": results,
    }


def list_runs(*, tenant_slug: str, limit: int = 30) -> Dict[str, Any]:
    tenant_slug = (tenant_slug or "default").strip()
    with Session(get_engine()) as db:
        rows = list(
            db.exec(
                select(WorkflowRun)
                .where(WorkflowRun.tenant_slug == tenant_slug)
                .order_by(WorkflowRun.created_at.desc())
                .limit(limit)
            )
        )
    return {
        "runs": [
            {
                "id": r.id,
                "name": r.name,
                "trigger": r.trigger,
                "status": r.status,
                "step_count": r.step_count,
                "approvals_opened": r.approvals_opened,
                "elapsed_ms": r.elapsed_ms,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }
