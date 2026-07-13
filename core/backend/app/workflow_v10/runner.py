# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Phase 1 / S19-close — Workflow execution runner (stub).

Real Inngest integration is the Sprint 21 follow-up; this stub gives the
HTTP surface enough behaviour for end-to-end customer-journey smoke:

- `plan(workflow)`            → ordered step list + per-node estimate
- `estimate(plan)`            → total seconds (sum of step `estimate_s`)
- `enqueue(workflow, tenant)` → job_id (uuid hex), persisted in-memory until
                                a real queue ships
- `status(job_id)`            → `{state: queued|running|done, ...}`

The shape matches the Sprint 19 brief so the API layer doesn't change when
the real runner lands.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# hitl approval-role hierarchy. A node's ``approval_role`` requires AT LEAST
# this rank; the approver's resolved role must meet or exceed it. "tenant_owner"
# (what every shipped template uses) and "admin"/"owner" are the top tier — in
# a single-tenant deploy the bootstrap admin IS the owner. An unknown required
# role fails closed to the top tier so a typo can't accidentally open the gate.
_ROLE_RANK = {"member": 1, "manager": 2, "admin": 3, "owner": 3, "tenant_owner": 3}


def _role_satisfies(caller_role: Optional[str], required_role: Optional[str]) -> bool:
    """True when ``caller_role`` is allowed to approve a gate requiring
    ``required_role``. No required role → no gate (legacy hitl nodes)."""
    if not required_role:
        return True
    req = _ROLE_RANK.get(str(required_role).strip().lower(), 3)
    have = _ROLE_RANK.get(str(caller_role or "").strip().lower(), 0)
    return have >= req


_PER_KIND_ESTIMATE_S: Dict[str, float] = {
    "trigger": 0.05,
    "llm_call": 1.5,
    "api_request": 0.4,
    "conditional": 0.05,
    "loop": 0.4,
    "hitl": 0.0,  # blocked on human, not measurable
    "abs_tool": 0.6,
    "transform": 0.1,
    "output": 0.05,
}


# BUG-V2 — Per-call USD cost estimate (PROMISE.md: "Estimated cost per
# run: $X.XX shows zero for free-tier-only workflows").
#
# Free providers (Groq, Cloudflare, Gemini, Cohere, Ollama, local) all
# resolve to $0.0. Paid providers are priced per call so a single-node
# workflow surfaces a non-zero estimate; refine to per-token once the
# adapter pipeline reports planned token budgets.
_FREE_PROVIDERS = frozenset(
    {"groq", "cloudflare", "gemini", "cohere", "ollama", "local", "mlx"}
)
_PAID_PER_CALL_USD: Dict[str, float] = {
    # Anthropic — assumes a typical 2K-in / 1K-out workflow node, sized to
    # match Anthropic's published pricing (Sonnet 4.x baseline).
    "claude-haiku": 0.0001,
    "claude-sonnet": 0.0005,
    "claude-opus": 0.0030,
    "anthropic": 0.0005,  # generic anthropic node default → sonnet baseline
    # OpenAI parity (kept conservative — surfaced when caller opts into a
    # paid OpenAI provider via the cascade).
    "openai": 0.0008,
    "gpt-4": 0.0015,
}


def _node_cost_usd(node: Dict[str, Any]) -> float:
    """Return the per-call USD cost for a single workflow node.

    Resolution order:
      1. Explicit `provider` / `model` config on the node.
      2. `kind`-level fallback (only `llm_call` can incur a cost).
      3. Default $0 (free path).
    """
    config = node.get("config") or {}
    raw = (
        str(config.get("model") or "")
        + " "
        + str(config.get("provider") or "")
        + " "
        + str(node.get("provider") or "")
    ).lower()
    # Free path short-circuit.
    for free in _FREE_PROVIDERS:
        if free in raw:
            return 0.0
    # Paid lookup (most-specific key wins).
    for key, price in sorted(_PAID_PER_CALL_USD.items(), key=lambda kv: -len(kv[0])):
        if key in raw:
            return price
    # No provider hint → cost is 0 unless the node kind is explicitly
    # an LLM call with no provider (treated as free path baseline).
    return 0.0


def estimate_cost(plan_steps: List[Dict[str, Any]]) -> float:
    """Sum the per-node USD cost across the plan.

    Returns a float rounded to 4 decimals so the UI can render
    "$0.0001" without trailing-zero noise.
    """
    total = 0.0
    for step in plan_steps:
        node = step.get("node") or {}
        if not node:
            # Plan rows don't carry the original node; rebuild a thin
            # surrogate from the planned fields so the lookup still
            # works for cascade-tagged kinds.
            node = {
                "kind": step.get("kind"),
                "config": {
                    "provider": step.get("provider"),
                    "model": step.get("model"),
                },
            }
        total += _node_cost_usd(node)
    return round(total, 4)


@dataclass
class JobRecord:
    job_id: str
    tenant_slug: str
    workflow: Dict[str, Any]
    state: str = "queued"
    enqueued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    node_outputs: Dict[str, Any] = field(default_factory=dict)
    pending_node: Optional[str] = None  # hitl node awaiting human approval
    warnings: List[str] = field(default_factory=list)  # e.g. unsupported nodes


_JOBS: Dict[str, JobRecord] = {}


def plan(workflow: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Topologically order nodes (best-effort linear order) + estimate."""
    nodes = workflow.get("nodes", [])
    edges = workflow.get("edges", [])

    # Build adjacency: id -> outgoing
    out_edges: Dict[str, List[str]] = {n["id"]: [] for n in nodes}
    in_count: Dict[str, int] = {n["id"]: 0 for n in nodes}
    for e in edges:
        src, dst = e.get("source") or e.get("from"), e.get("target") or e.get("to")
        if src in out_edges and dst is not None:
            out_edges[src].append(dst)
            in_count[dst] = in_count.get(dst, 0) + 1

    # Kahn topo sort
    queue = [n["id"] for n in nodes if in_count.get(n["id"], 0) == 0]
    order: List[str] = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for nxt in out_edges.get(nid, []):
            in_count[nxt] -= 1
            if in_count[nxt] == 0:
                queue.append(nxt)
    # Append any remainder (cycle members) at the end so we still return a list.
    for n in nodes:
        if n["id"] not in order:
            order.append(n["id"])

    by_id = {n["id"]: n for n in nodes}
    return [
        {
            "step": idx + 1,
            "node_id": nid,
            "kind": by_id.get(nid, {}).get("kind", "unknown"),
            "name": by_id.get(nid, {}).get("name") or nid,
            "estimate_s": _PER_KIND_ESTIMATE_S.get(
                by_id.get(nid, {}).get("kind", ""), 0.5
            ),
            # BUG-V2 — carry the source node so estimate_cost() can
            # inspect provider/model config without re-walking the
            # workflow.
            "node": by_id.get(nid, {}),
        }
        for idx, nid in enumerate(order)
    ]


def estimate(plan_steps: List[Dict[str, Any]]) -> float:
    return round(sum(s.get("estimate_s", 0.0) for s in plan_steps), 2)


async def enqueue(workflow: Dict[str, Any], tenant_slug: str = "default") -> str:
    """Queue the workflow. Stub: stores record + returns job_id immediately.
    Real runner: pushes to Inngest, stores correlation id."""
    job_id = uuid.uuid4().hex
    record = JobRecord(
        job_id=job_id,
        tenant_slug=tenant_slug,
        workflow=workflow,
    )
    _JOBS[job_id] = record
    logger.info(
        "workflow_enqueue tenant=%s job=%s nodes=%d",
        tenant_slug,
        job_id,
        len(workflow.get("nodes", [])),
    )
    # Phase-1.5 — real linear execution: llm_call nodes hit the cascade for
    # real; other kinds are recorded (hitl/abs_tool/api_request are noted as
    # pending for the durable engine follow-up).
    asyncio.create_task(_execute_run(job_id))
    return job_id


_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _node_text(out: Any) -> str:
    """Best-effort text of a prior node's output for templating."""
    if isinstance(out, dict):
        return str(out.get("text") or out.get("error") or out.get("skipped") or "")
    return str(out or "")


def _render(template: str, outputs: Dict[str, Any]) -> str:
    """Substitute `{{node_id}}` placeholders with that node's prior output.
    Unknown placeholders are left intact so a bad ref doesn't silently vanish."""

    def repl(m: "re.Match[str]") -> str:
        key = m.group(1).strip()
        # accept `id`, `steps.id`, `steps.id.output` shapes → take the id token
        token = key.split(".")[1] if key.startswith("steps.") else key
        if token in outputs:
            return _node_text(outputs[token])
        return m.group(0)

    return _TEMPLATE_RE.sub(repl, template)


async def _run_node(
    node: Dict[str, Any], kind: str, outputs: Dict[str, Any], tenant: str
) -> Dict[str, Any]:
    config = node.get("config") or {}
    if kind == "llm_call":
        from app.cascade.orchestrator import call_with_cascade

        prompt = _render(
            str(
                config.get("prompt_template")
                or config.get("prompt")
                or node.get("name")
                or ""
            ),
            outputs,
        )
        if not prompt.strip():
            return {"skipped": kind, "note": "empty prompt_template"}
        provider = str(config.get("provider") or node.get("provider") or "groq")
        model = config.get("model") or node.get("model")
        resp = await call_with_cascade(
            prompt, primary=provider, model=model, tenant_id=tenant or "default"
        )
        return {"text": getattr(resp, "text", None) or str(resp), "provider": provider}
    if kind == "trigger":
        # Trigger carries the workflow's initial input so downstream
        # {{trigger-id}} references resolve to something.
        text = str(
            config.get("input")
            or config.get("payload")
            or node.get("description")
            or ""
        )
        return {"text": text, "kind": "trigger"}
    if kind == "api_request":
        return await _run_api_request(node, config, outputs)
    if kind == "abs_tool":
        return await _run_abs_tool(config, outputs, tenant)
    if kind == "conditional":
        from app.workflow_v10.condition_eval import ConditionError, evaluate

        expr = str(config.get("condition_expr") or config.get("condition") or "")
        try:
            result = evaluate(expr, outputs)
        except ConditionError as exc:
            return {"error": f"bad condition: {exc}", "kind": "conditional"}
        return {"result": result, "text": str(result).lower(), "kind": "conditional"}
    if kind in ("output", "transform"):
        # Pass-through — surface a templated body if one is configured.
        body = (
            config.get("output_template")
            or config.get("template")
            or config.get("body")
            or ""
        )
        return {"text": _render(str(body), outputs), "passthrough": kind}
    if kind == "loop":
        # The linear v1 engine cannot iterate. Returning a silent "skipped"
        # here made a workflow containing a loop finish as a clean success
        # while the loop body ran ZERO times — e.g. the "Each supplier"
        # template notified nobody yet reported "done". Surface it as an
        # explicit unsupported error so the run is honestly flagged as
        # incomplete instead of falsely green. Real iteration is the
        # durable-engine follow-up.
        return {
            "error": (
                "loop nodes are not executed by the linear engine — the loop "
                "body runs zero iterations (durable-engine follow-up)"
            ),
            "kind": "loop",
            "unsupported": True,
        }
    # Any kind the engine doesn't implement. Surfacing it as an explicit
    # unsupported error (like `loop`) keeps an unknown/typo'd node from
    # finishing the run as a false green — the same honesty fix applied above.
    return {
        "error": f"node kind '{kind}' is not executed by the linear engine",
        "kind": kind,
        "unsupported": True,
    }


async def _run_api_request(
    node: Dict[str, Any], config: Dict[str, Any], outputs: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute an ``api_request`` node: a real, SSRF-guarded outbound HTTP call.

    URL + body are templated from upstream node outputs. The target is rejected
    if it resolves to a non-public address (cloud metadata / internal services).
    Honours the node's ``timeout_s`` and retries up to ``retry_max`` times on
    transient failure.
    """
    import httpx

    from app.workflow_v10.net_guard import UnsafeUrlError, assert_safe_url

    url = _render(str(config.get("url") or ""), outputs).strip()
    if not url:
        return {"skipped": "api_request", "note": "no url configured"}
    method = str(config.get("method") or "GET").upper()
    # NodeConfig forbids extra fields, so a request body (when present) is
    # carried in `prompt` and templated like any other text.
    body = _render(str(config.get("prompt") or ""), outputs)
    timeout = float(node.get("timeout_s", 60) or 60)
    retry_max = int(node.get("retry_max", 0) or 0)

    try:
        assert_safe_url(url)
    except UnsafeUrlError as exc:
        return {"error": f"blocked unsafe url: {exc}", "kind": "api_request"}

    last_exc: Optional[str] = None
    for attempt in range(retry_max + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False
            ) as client:
                kwargs: Dict[str, Any] = {}
                if body and method in ("POST", "PUT", "PATCH"):
                    kwargs["content"] = body
                resp = await client.request(method, url, **kwargs)
            return {
                "text": resp.text[:20000],
                "status_code": resp.status_code,
                "kind": "api_request",
                "attempts": attempt + 1,
            }
        except httpx.HTTPError as exc:
            last_exc = str(exc)[:200]
            logger.warning(
                "api_request node %s attempt %d failed: %s",
                node.get("id"),
                attempt + 1,
                last_exc,
            )
    return {
        "error": f"request failed after {retry_max + 1} attempt(s): {last_exc}",
        "kind": "api_request",
    }


# abs_tool names the engine can invoke for real. External / side-effecting
# integrations (slack_post, gmail_send, ...) are NOT here — those need a
# marketplace plugin, and abs_tool returns an honest "not available" rather
# than pretending the side effect happened.
_RAG_TOOLS = frozenset({"rag_query", "rag.query", "query", "abs.rag_query"})
_STATUS_TOOLS = frozenset({"system_status", "abs.system_status", "status"})


async def _run_abs_tool(
    config: Dict[str, Any], outputs: Dict[str, Any], tenant: str
) -> Dict[str, Any]:
    """Invoke a real, read-only ABS tool by name.

    Supported: RAG query (knowledge base), system status, and any ``ask*`` /
    delegation name (routed through the cascade). Anything else returns an
    honest not-available error — the engine never fakes a side effect.
    """
    raw_name = str(config.get("tool_name") or "").strip()
    name = raw_name.lower()
    short = name.split(".")[-1]
    args = config.get("tool_args") or {}

    if name in _RAG_TOOLS or short in _RAG_TOOLS:
        from app.rag import query as rag_query_fn

        question = _render(
            str(
                args.get("question") or args.get("query") or config.get("prompt") or ""
            ),
            outputs,
        )
        if not question.strip():
            return {"skipped": "abs_tool", "note": "rag_query: empty question"}
        top_k = int(args.get("top_k", 5) or 5)
        res = await rag_query_fn(question, top_k=top_k)
        import json as _json

        text = res if isinstance(res, str) else _json.dumps(res, ensure_ascii=False)
        return {"text": text, "tool": raw_name, "kind": "abs_tool"}

    if name in _STATUS_TOOLS or short in _STATUS_TOOLS:
        from app.mcp.tools.system import system_status

        import json as _json

        res = await system_status()
        text = (
            res
            if isinstance(res, str)
            else _json.dumps(res, ensure_ascii=False, default=str)
        )
        return {"text": text, "tool": raw_name, "kind": "abs_tool"}

    if short.startswith("ask") or short in ("llm", "cascade"):
        from app.cascade.orchestrator import call_with_cascade

        prompt = _render(
            str(
                args.get("prompt") or args.get("question") or config.get("prompt") or ""
            ),
            outputs,
        )
        if not prompt.strip():
            return {"skipped": "abs_tool", "note": f"{raw_name}: empty prompt"}
        # ask_<provider> → primary provider; bare "ask" → default groq.
        provider = str(
            args.get("provider")
            or (short[4:] if short.startswith("ask_") else "")
            or "groq"
        )
        resp = await call_with_cascade(
            prompt, primary=provider, tenant_id=tenant or "default"
        )
        return {
            "text": getattr(resp, "text", None) or str(resp),
            "tool": raw_name,
            "kind": "abs_tool",
        }

    return {
        "error": (
            f"abs_tool {raw_name!r} not available in the workflow engine — "
            "external/side-effecting tools require a marketplace plugin"
        ),
        "kind": "abs_tool",
    }


_TRUE_LABELS = frozenset({"true", "yes", "1", "y", "t", "ok", "pass"})
_FALSE_LABELS = frozenset({"false", "no", "0", "n", "f", "fail"})


def _edge_fires(edge: Dict[str, Any], source_output: Any) -> bool:
    """Decide whether *edge* propagates reachability to its target.

    Backwards-compatible: an edge with no ``condition`` always fires (so a
    workflow without any conditions runs every node, exactly as before). A
    labelled edge off a ``conditional`` node fires only on the matching branch.
    """
    cond = str(edge.get("condition") or "").strip()
    if not cond:
        return True
    result = source_output.get("result") if isinstance(source_output, dict) else None
    label = cond.lower()
    if isinstance(result, bool):
        if label in _TRUE_LABELS:
            return result is True
        if label in _FALSE_LABELS:
            return result is False
        return False  # labelled edge that doesn't name a known branch
    # Non-conditional source: treat the label as an equality guard on its text.
    return cond == _node_text(source_output)


async def _execute_run(job_id: str) -> None:
    record = _JOBS.get(job_id)
    if record is None:
        return
    record.state = "running"
    if record.started_at is None:  # preserve original start across resume
        record.started_at = time.time()
    try:
        steps = plan(record.workflow)
        edges = record.workflow.get("edges", []) or []
        out_edges: Dict[str, List[Dict[str, Any]]] = {}
        has_incoming: set[str] = set()
        for e in edges:
            src = e.get("source") or e.get("from")
            dst = e.get("target") or e.get("to")
            if src is None or dst is None:
                continue
            out_edges.setdefault(src, []).append(e)
            has_incoming.add(dst)

        # Roots (no incoming edge) are always reachable. Every other node must
        # be reached through a firing edge.
        reachable: set[str] = {
            nid
            for s in steps
            if (nid := s.get("node_id")) is not None and nid not in has_incoming
        }

        for step in steps:
            nid = step.get("node_id")
            kind = str(step.get("kind") or "unknown")
            node = step.get("node") or {}
            if nid not in reachable:
                record.node_outputs[nid] = {
                    "skipped": "unreached",
                    "note": "branch not taken (upstream condition routed elsewhere)",
                }
                continue

            prior = record.node_outputs.get(nid)

            # hitl gate — pause the whole run until a human approves/rejects.
            if kind == "hitl":
                role = (node.get("config") or {}).get("approval_role")
                decision = prior if isinstance(prior, dict) else {}
                if decision.get("rejected") is True:
                    # rejected: record + do NOT propagate (downstream unreached).
                    # Preserve the approver identity recorded by resume() — re-
                    # executing the gate must not wipe the audit trail.
                    record.node_outputs[nid] = {
                        "rejected": True,
                        "kind": "hitl",
                        "approval_role": role,
                        "rejected_by": decision.get("rejected_by"),
                    }
                    continue
                if decision.get("approved") is not True:
                    # not yet decided → pause and wait for resume()
                    record.state = "awaiting_approval"
                    record.pending_node = nid
                    record.node_outputs[nid] = {
                        "awaiting": "approval",
                        "kind": "hitl",
                        "approval_role": role,
                    }
                    return
                output = {
                    "approved": True,
                    "kind": "hitl",
                    "approval_role": role,
                    "approved_by": decision.get("approved_by"),
                }
                record.node_outputs[nid] = output
                for e in out_edges.get(nid, []):
                    if _edge_fires(e, output):
                        dst = e.get("target") or e.get("to")
                        if dst is not None:
                            reachable.add(dst)
                continue

            # Resume reuse: a node already executed in a previous pass keeps its
            # output (never re-run a side effect like api_request/abs_tool). Only
            # real results are reused — "unreached"/"awaiting" markers re-evaluate.
            if (
                isinstance(prior, dict)
                and not prior.get("awaiting")
                and prior.get("skipped") != "unreached"
            ):
                output = prior
            else:
                try:
                    output = await _run_node(
                        node, kind, record.node_outputs, record.tenant_slug
                    )
                except Exception as exc:  # one node failing must not abort the run
                    logger.warning("workflow node %s (%s) failed: %s", nid, kind, exc)
                    output = {"error": str(exc)[:300]}
            record.node_outputs[nid] = output
            if isinstance(output, dict) and output.get("unsupported"):
                record.warnings.append(
                    f"node {nid} ({kind}) not executed: {output.get('error', 'unsupported')}"
                )
            elif isinstance(output, dict) and output.get("error"):
                # A node that raised must not abort the run (best-effort), but
                # its failure must NOT be silent: surface it in warnings so the
                # caller/panel sees it instead of a green "done" hiding an error
                # buried in node_outputs.
                record.warnings.append(f"node {nid} ({kind}) failed: {output['error']}")
            for e in out_edges.get(nid, []):
                if _edge_fires(e, output):
                    dst = e.get("target") or e.get("to")
                    if dst is not None:
                        reachable.add(dst)
        record.state = "done"
        record.pending_node = None
    except Exception as exc:  # pragma: no cover — planner/setup failure
        logger.warning("workflow run %s failed: %s", job_id, exc)
        record.state = "error"
        record.error = str(exc)[:300]
    record.completed_at = time.time()


def status(job_id: str) -> Optional[Dict[str, Any]]:
    record = _JOBS.get(job_id)
    if record is None:
        return None
    return {
        "job_id": record.job_id,
        "tenant_slug": record.tenant_slug,
        "state": record.state,
        "enqueued_at": record.enqueued_at,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "error": record.error,
        "node_outputs": record.node_outputs,
        "pending_node": record.pending_node,
        "warnings": record.warnings,
    }


async def resume(
    job_id: str,
    *,
    approved: bool,
    role: Optional[str] = None,
    actor: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Approve or reject a paused ``hitl`` node and continue the run.

    ``role`` is the approver's resolved role and is enforced against the gated
    node's ``approval_role`` — a member cannot approve a gate that requires an
    owner. ``actor`` (the approver's identity, e.g. email) is recorded for the
    audit trail. Returns ``None`` if the job is unknown, an error dict if it is
    not awaiting approval or the role is insufficient, else a dict echoing the
    decision.
    """
    record = _JOBS.get(job_id)
    if record is None:
        return None
    if record.state != "awaiting_approval" or not record.pending_node:
        return {"error": "job is not awaiting approval", "state": record.state}
    nid = record.pending_node
    pending = record.node_outputs.get(nid)
    required_role = pending.get("approval_role") if isinstance(pending, dict) else None
    if not _role_satisfies(role, required_role):
        # do NOT record a decision or resume — the gate stays pending so an
        # authorised approver can still act.
        return {
            "error": "approval_role_required",
            "required_role": required_role,
            "role": role,
        }
    record.node_outputs[nid] = (
        {
            "approved": True,
            "kind": "hitl",
            "approved_by": actor or role,
            "approval_role": required_role,
        }
        if approved
        else {
            "rejected": True,
            "kind": "hitl",
            "rejected_by": actor or role,
            "approval_role": required_role,
        }
    )
    record.pending_node = None
    record.state = "running"
    record.completed_at = None
    await _execute_run(job_id)
    return {
        "job_id": job_id,
        "resumed_node": nid,
        "approved": approved,
        "state": record.state,
    }


def reset_for_tests() -> None:
    _JOBS.clear()


__all__ = [
    "JobRecord",
    "enqueue",
    "estimate",
    "estimate_cost",
    "plan",
    "reset_for_tests",
    "resume",
    "status",
]
