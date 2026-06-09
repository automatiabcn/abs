# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/agentic-workflows — run an agent chain + palette + run history.

Backs the Workflow Designer screen (the agentic path). Tenant from principal.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agentic_workflows import (
    get_definition,
    list_runs,
    palette,
    run_workflow,
    save_definition,
)
from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context

router = APIRouter(prefix="/v1/agentic-workflows", tags=["agentic-workflows"])


def _tenant(auth: AuthContext) -> str:
    return (auth.tenant_id or "default").strip() or "default"


@router.get("/palette")
async def get_palette(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return palette()


@router.get("/definition")
async def get_definition_endpoint(
    key: str = "default",
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return get_definition(tenant_slug=_tenant(auth), key=key)


class SaveDefRequest(BaseModel):
    key: str = Field(default="default", max_length=64)
    name: str = Field(default="", max_length=200)
    graph: Dict[str, Any] = Field(default_factory=dict)


@router.put("/definition")
async def save_definition_endpoint(
    body: SaveDefRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return save_definition(
        tenant_slug=_tenant(auth), key=body.key, name=body.name, graph=body.graph,
    )


@router.get("/runs")
async def get_runs(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return list_runs(tenant_slug=_tenant(auth))


class RunRequest(BaseModel):
    name: str = Field(default="agentic-run", max_length=200)
    steps: List[str] = Field(..., min_length=1, max_length=20)
    input: str = Field(..., min_length=1, max_length=8000)
    trigger: str = Field(default="manual", max_length=32)


@router.post("/run")
async def run_endpoint(
    body: RunRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return await run_workflow(
        tenant_slug=_tenant(auth), name=body.name, steps=body.steps,
        input_text=body.input, trigger=body.trigger, actor=auth.subject,
    )
