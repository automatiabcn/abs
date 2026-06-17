# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/leads — Lead Intelligence: account-priority list + scoring.

Backs the Lead Intelligence screen. Tenant from the authenticated principal.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.leads import create_company, create_lead, get_lead, list_leads, score_lead

router = APIRouter(prefix="/v1/leads", tags=["leads"])


def _tenant(auth: AuthContext) -> str:
    return (auth.tenant_id or "default").strip() or "default"


@router.get("")
async def list_lead_priority(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return list_leads(tenant_slug=_tenant(auth))


class CreateLeadRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=256)
    sector: str = Field(default="", max_length=96)
    domain: str = Field(default="", max_length=128)
    location: str = Field(default="", max_length=128)
    size: str = Field(default="", max_length=32)
    source: str = Field(default="manual", max_length=64)
    consent_status: str = Field(default="", max_length=32)


@router.post("")
async def create_lead_endpoint(
    body: CreateLeadRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    tenant = _tenant(auth)
    company_id = create_company(
        tenant_slug=tenant, name=body.company_name, sector=body.sector,
        source=body.source, domain=body.domain or None,
        location=body.location, size=body.size,
    )
    return create_lead(
        tenant_slug=tenant, company_id=company_id, source=body.source,
        owner=auth.subject, consent_status=body.consent_status,
    )


@router.get("/{lead_id}")
async def get_lead_endpoint(
    lead_id: int,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    row = get_lead(tenant_slug=_tenant(auth), lead_id=lead_id)
    if row is None:
        raise HTTPException(404, "lead_not_found")
    return row


@router.post("/{lead_id}/score")
async def score_lead_endpoint(
    lead_id: int,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    row = await score_lead(tenant_slug=_tenant(auth), lead_id=lead_id, actor=auth.subject)
    if row is None:
        raise HTTPException(404, "lead_not_found")
    return row
