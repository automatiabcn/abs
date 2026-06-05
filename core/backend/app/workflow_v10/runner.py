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


_PER_KIND_ESTIMATE_S: Dict[str, float] = {
    "trigger": 0.05,
    "llm_call": 1.5,
    "api_request": 0.4,
    "conditional": 0.05,
    "loop": 0.4,
    "hitl": 0.0,         # blocked on human, not measurable
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
    for key, price in sorted(
        _PAID_PER_CALL_USD.items(), key=lambda kv: -len(kv[0])
    ):
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
            str(config.get("prompt_template") or config.get("prompt") or node.get("name") or ""),
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
            config.get("input") or config.get("payload") or node.get("description") or ""
        )
        return {"text": text, "kind": "trigger"}
    if kind == "api_request":
        return await _run_api_request(node, config, outputs)
    if kind in ("output", "transform", "conditional"):
        # Pass-through — surface a templated body if one is configured.
        body = (
            config.get("output_template")
            or config.get("template")
            or config.get("body")
            or ""
        )
        return {"text": _render(str(body), outputs), "passthrough": kind}
    # hitl / abs_tool / loop — not run by the linear v1 engine.
    return {"skipped": kind, "note": "not executed by the linear v1 engine (durable engine follow-up)"}


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
    return {"error": f"request failed after {retry_max + 1} attempt(s): {last_exc}", "kind": "api_request"}


async def _execute_run(job_id: str) -> None:
    record = _JOBS.get(job_id)
    if record is None:
        return
    record.state = "running"
    record.started_at = time.time()
    try:
        steps = plan(record.workflow)
        for step in steps:
            nid = step.get("node_id")
            kind = str(step.get("kind") or "unknown")
            node = step.get("node") or {}
            try:
                record.node_outputs[nid] = await _run_node(
                    node, kind, record.node_outputs, record.tenant_slug
                )
            except Exception as exc:  # one node failing must not abort the run
                logger.warning("workflow node %s (%s) failed: %s", nid, kind, exc)
                record.node_outputs[nid] = {"error": str(exc)[:300]}
        record.state = "done"
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
    "status",
]
