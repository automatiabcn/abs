# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Human-in-the-loop approval flow + panel-session→OAuth subject bridge.

Panel session cookies map to an OAuth subject so
`/v1/*` endpoints can run for a logged-in panel user without a separate
JWT. The mapper is provider-agnostic — any caller-supplied `session_lookup`
returning `(subject, tenant_id, roles)` is fine.

Approval ledger lifetime in-memory; production swaps to a DB row + Slack
button webhook.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = [
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalLedger",
    "PanelSessionPrincipal",
    "panel_session_to_principal",
]


@dataclass(slots=True)
class PanelSessionPrincipal:
    subject: str
    tenant_id: str
    roles: list[str]


def panel_session_to_principal(
    *,
    session_id: str,
    session_lookup: Callable[[str], dict[str, Any] | None],
) -> PanelSessionPrincipal:
    """Translate a panel session cookie into a principal usable by /v1/* deps."""

    if not session_id:
        raise ValueError("session_id required")
    record = session_lookup(session_id)
    if record is None:
        raise KeyError(f"session_id {session_id!r} not found")
    subject = str(record.get("subject") or record.get("user_id") or "")
    tenant = str(record.get("tenant_id") or "")
    roles_raw = record.get("roles") or ["member"]
    roles = (
        [r.strip() for r in roles_raw.split(",") if r.strip()]
        if isinstance(roles_raw, str)
        else list(roles_raw)
    )
    if not subject or not tenant:
        raise ValueError("session payload must include subject + tenant_id")
    return PanelSessionPrincipal(subject=subject, tenant_id=tenant, roles=roles)


@dataclass(slots=True)
class ApprovalRequest:
    request_id: str
    tenant_id: str
    subject: str
    requester: str
    payload: dict[str, Any]
    created_at: float
    auto_escalate_after_seconds: int = 4 * 3600


@dataclass(slots=True)
class ApprovalDecision:
    request_id: str
    approved: bool
    decided_by: str
    decided_at: float
    note: str = ""


class ApprovalLedger:
    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}
        self._decisions: dict[str, ApprovalDecision] = {}

    def request(
        self,
        *,
        tenant_id: str,
        subject: str,
        requester: str,
        payload: dict[str, Any],
        auto_escalate_after_seconds: int = 4 * 3600,
    ) -> ApprovalRequest:
        if not tenant_id or not requester:
            raise ValueError("tenant_id and requester required")
        record = ApprovalRequest(
            request_id=uuid.uuid4().hex[:12],
            tenant_id=tenant_id,
            subject=subject,
            requester=requester,
            payload=payload,
            created_at=time.time(),
            auto_escalate_after_seconds=auto_escalate_after_seconds,
        )
        self._requests[record.request_id] = record
        logger.info(
            "approval_request id=%s tenant=%s requester=%s",
            record.request_id,
            tenant_id,
            requester,
        )
        return record

    def decide(
        self,
        *,
        request_id: str,
        approved: bool,
        decided_by: str,
        note: str = "",
    ) -> ApprovalDecision:
        record = self._requests.get(request_id)
        if record is None:
            raise KeyError(f"approval {request_id!r} not found")
        decision = ApprovalDecision(
            request_id=request_id,
            approved=approved,
            decided_by=decided_by,
            decided_at=time.time(),
            note=note,
        )
        self._decisions[request_id] = decision
        logger.info(
            "approval_decision id=%s approved=%s by=%s",
            request_id,
            approved,
            decided_by,
        )
        return decision

    def get_decision(self, request_id: str) -> ApprovalDecision | None:
        return self._decisions.get(request_id)

    def is_overdue(self, request_id: str, *, now: float | None = None) -> bool:
        record = self._requests.get(request_id)
        if record is None or request_id in self._decisions:
            return False
        clock = now if now is not None else time.time()
        return clock - record.created_at >= record.auto_escalate_after_seconds
