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
    # Schedule a faux completion to mimic eventual consistency.
    asyncio.create_task(_simulate_run(job_id))
    return job_id


async def _simulate_run(job_id: str) -> None:
    record = _JOBS.get(job_id)
    if record is None:
        return
    record.state = "running"
    record.started_at = time.time()
    # Simulate the planned work duration capped at 1 s for tests.
    plan_steps = plan(record.workflow)
    delay = min(estimate(plan_steps), 1.0)
    await asyncio.sleep(delay)
    record.state = "done"
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
    }


def reset_for_tests() -> None:
    _JOBS.clear()


__all__ = [
    "JobRecord",
    "enqueue",
    "estimate",
    "plan",
    "reset_for_tests",
    "status",
]
