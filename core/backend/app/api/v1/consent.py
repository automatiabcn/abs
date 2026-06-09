# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/consent — Consent Ledger: set/get per-contact consent + channel gate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.consent import check_channel, get_consent, set_consent

router = APIRouter(prefix="/v1/consent", tags=["consent"])


def _tenant(auth: AuthContext) -> str:
    return (auth.tenant_id or "default").strip() or "default"


class ConsentRequest(BaseModel):
    email_consent: bool = False
    phone_consent: bool = False
    sms_consent: bool = False
    whatsapp_consent: bool = False
    do_not_call: bool = False
    opt_in_source: str = Field(default="", max_length=64)
    legal_basis: str = Field(default="", max_length=48)
    consent_evidence: str = Field(default="", max_length=512)


@router.put("/{contact_email}")
async def set_consent_endpoint(
    contact_email: str,
    body: ConsentRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return set_consent(
        tenant_slug=_tenant(auth), contact_email=contact_email, **body.model_dump()
    )


@router.get("/{contact_email}")
async def get_consent_endpoint(
    contact_email: str,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    rec = get_consent(tenant_slug=_tenant(auth), contact_email=contact_email)
    if rec is None:
        raise HTTPException(404, "consent_not_found")
    return rec


@router.get("/{contact_email}/check")
async def check_channel_endpoint(
    contact_email: str,
    channel: str,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return check_channel(
        tenant_slug=_tenant(auth), contact_email=contact_email, channel=channel
    )
