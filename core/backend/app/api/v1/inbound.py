# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/inbound + /v1/knowledge — the MVP slice (Inbound Intelligence + Knowledge
Base Agent). Both sit on the Agent Runtime; tenant from the principal."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agents.runtime import run_agent
from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.inbound import triage_inbound

logger = logging.getLogger(__name__)

router = APIRouter(tags=["growth-mvp"])


def _tenant(auth: AuthContext) -> str:
    return (auth.tenant_id or "default").strip() or "default"


class InboundRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    channel: str = Field(default="web", max_length=32)
    from_email: str = Field(default="", max_length=254)
    project_slug: Optional[str] = None


@router.post("/v1/inbound")
async def inbound_triage(
    body: InboundRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    """Classify an incoming request + draft a source-cited reply (→ Approval)."""
    return await triage_inbound(
        body.message,
        tenant_slug=_tenant(auth),
        channel=body.channel,
        from_email=body.from_email,
        project_slug=body.project_slug,
        actor=auth.subject,
    )


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=8000)
    project_slug: Optional[str] = None


@router.post("/v1/knowledge/ask")
async def knowledge_ask(
    body: AskRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    """Knowledge Base Agent — a source-cited answer from the tenant's corpus."""
    res = await run_agent(
        "knowledge_base",
        body.question,
        tenant_id=_tenant(auth),
        project_slug=body.project_slug,
        user_subject=auth.subject,
    )
    out = {
        "answer": res.summary,
        "citations": [e.to_dict() for e in res.evidence],
        "confidence": res.confidence,
        "provider": res.provider,
    }
    try:
        from app.approvals import log_agent_run

        out["run_id"] = log_agent_run(
            res, tenant_slug=_tenant(auth), actor=auth.subject, task=body.question
        )
    except Exception:  # noqa: BLE001 — best-effort
        logger.info("knowledge run persistence skipped", exc_info=True)
    return out
