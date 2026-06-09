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
from app.db.growth_models import WorkflowRun
from app.db.session import get_engine

logger = logging.getLogger(__name__)


def palette() -> Dict[str, Any]:
    """Node palette for the designer: agents (by category) + node kinds."""
    grouped = agents_by_category()
    return {
        "agents": {
            cat: [{"id": a.id, "name": a.name, "risk": a.risk} for a in items]
            for cat, items in grouped.items()
        },
        "node_kinds": ["trigger", "agent", "retrieval", "connector",
                       "policy", "approval", "action", "branch", "sub_workflow"],
    }


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
