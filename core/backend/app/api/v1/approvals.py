# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/approvals — Approval Center API.

Lists the risky agent actions awaiting human approval (with each agent's
rationale + evidence + risk + consent + policy result) and records the
reviewer's decision. Tenant from the authenticated principal only.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.actions import list_actions
from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.approvals import decide_approval, get_approval, list_approvals
from app.approvals.service import AlreadyDecided
from app.observability.audit import emit_event

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


def _tenant(auth: AuthContext) -> str:
    return (auth.tenant_id or "default").strip() or "default"


@router.get("")
async def list_approval_items(
    status: str = "pending",
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    return list_approvals(tenant_slug=_tenant(auth), status=status)


@router.get("/outbox")
async def list_outbox(
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    """Action executions fired after approvals — the 'onay → aksiyon' trail."""
    return list_actions(tenant_slug=_tenant(auth))


@router.get("/{item_id}")
async def get_approval_item(
    item_id: int,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    row = get_approval(tenant_slug=_tenant(auth), item_id=item_id)
    if row is None:
        raise HTTPException(404, "approval_not_found")
    return row


class DecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject|edit)$")
    note: str = Field(default="", max_length=512)
    edited_message: str = Field(default="", max_length=8192)


@router.post("/{item_id}/decide")
async def decide_approval_item(
    item_id: int,
    body: DecisionRequest,
    auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
) -> dict:
    try:
        row = decide_approval(
            tenant_slug=_tenant(auth),
            item_id=item_id,
            decision=body.decision,
            decided_by=auth.subject,
            note=body.note,
            edited_message=body.edited_message,
        )
    except AlreadyDecided as exc:
        # 409, not 200: the caller asked to change something that is already
        # settled, and telling them it worked would be a lie the audit log has
        # to live with.
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if row is None:
        raise HTTPException(404, "approval_not_found")

    # A person let something out of this building, or stopped it. If one entry in
    # the whole log has to survive, it is this one — and until now the flow that
    # sends messages to a company's customers wrote nothing at all.
    emit_event(
        None,
        action="approval.decide",
        outcome="success",
        resource_type="approval",
        resource_id=str(item_id),
        user_id=auth.subject,
        tenant_id=_tenant(auth),
        reason=body.decision,
    )
    return row
