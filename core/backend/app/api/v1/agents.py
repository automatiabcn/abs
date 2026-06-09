# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/agents — Agent Registry API + Agent Runtime execution.

Serves the registry to the Agent Registry UI and runs an agent against a task.
Bearer JWT (multi-tenant clients / MCP) or the panel admin cookie both work, so
the operator console can drive it without minting a token by hand. The tenant is
taken from the authenticated principal — never the request body.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.registry import AGENTS, CATEGORY_LABELS, agents_by_category, get_agent
from app.agents.runtime import run_agent
from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context

router = APIRouter(prefix="/v1/agents", tags=["agents"])


def _tenant(auth: AuthContext) -> str:
    return (auth.tenant_id or "default").strip() or "default"


@router.get("")
async def list_agents(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    """The full registry grouped by category + runtime summary for the UI."""
    grouped = agents_by_category()
    categories = [
        {
            "key": cat,
            "label": CATEGORY_LABELS[cat],
            "agents": [a.to_dict() for a in grouped.get(cat, [])],
        }
        for cat in CATEGORY_LABELS
    ]
    total = len(AGENTS)
    approval_gated = sum(1 for a in AGENTS.values() if a.requires_approval)
    return {
        "total": total,
        "approval_gated": approval_gated,
        "categories": categories,
        "structured_output": "enforced",
    }


@router.get("/{agent_id}")
async def get_agent_detail(
    agent_id: str,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(404, "agent_not_found")
    return agent.to_dict()


class AgentRunRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=8000)
    project_slug: Optional[str] = None


@router.post("/{agent_id}/run")
async def run_agent_endpoint(
    agent_id: str,
    body: AgentRunRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    """Execute the agent against a task; returns its structured result. If the
    agent is approval-gated the result carries ``requires_approval=true`` and
    the proposed action for the Approval Center to persist."""
    if get_agent(agent_id) is None:
        raise HTTPException(404, "agent_not_found")
    try:
        result = await run_agent(
            agent_id,
            body.task,
            tenant_id=_tenant(auth),
            project_slug=body.project_slug,
            user_subject=auth.subject,
        )
    except KeyError:
        raise HTTPException(404, "agent_not_found")

    out = result.to_dict()
    # Persist the run + (if risky) open an Approval Center item. Best-effort:
    # a persistence hiccup must not fail the agent call itself.
    try:
        from app.approvals import create_approval_from_result, log_agent_run

        run_id = log_agent_run(
            result, tenant_slug=_tenant(auth), actor=auth.subject, task=body.task
        )
        out["run_id"] = run_id
        if result.requires_approval:
            out["approval"] = create_approval_from_result(
                result, tenant_slug=_tenant(auth), requester=auth.subject,
                agent_run_id=run_id,
            )
    except Exception:  # noqa: BLE001 — persistence is best-effort
        logging.getLogger(__name__).info("agent run persistence skipped", exc_info=True)
    return out
