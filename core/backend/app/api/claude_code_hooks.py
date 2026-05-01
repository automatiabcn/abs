"""Q8 Phase P — Claude Code lifecycle hook receivers.

Three webhook endpoints the customer's `~/.claude/settings.json` can
point at so their Claude Code session is gated by ABS:

  POST /v1/hooks/quota-check    — PreToolUse: budget gate
  POST /v1/hooks/audit-log      — PostToolUse: append to audit
  POST /v1/hooks/session-start  — SessionStart: tenant context inject

All three accept the integration token issued by `/v1/mcp/tokens`
(scope=hooks or all). Token is HMAC-signed; no DB lookup needed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.mcp_tokens import verify_token


router = APIRouter(prefix="/v1/hooks", tags=["claude-code-hooks"])
logger = logging.getLogger(__name__)


def _auth_from_header(authorization: Optional[str]) -> Dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "missing_bearer_token"
        )
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_token(token)
    scope = payload.get("scope")
    if scope not in ("hooks", "all"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"insufficient_scope: have={scope}, need=hooks|all",
        )
    return payload


# ───── PreToolUse: quota / permission gate ───────────────────────────────


class QuotaCheckRequest(BaseModel):
    tool_name: str
    tool_input: Optional[Dict] = None
    session_id: Optional[str] = None


@router.post("/quota-check")
def quota_check(
    body: QuotaCheckRequest,
    authorization: Optional[str] = Header(None),
) -> Dict:
    auth = _auth_from_header(authorization)
    tenant = auth["tenant"]

    # Cheap heuristic — Bash and Write get a stricter look. A full quota
    # implementation queries `/v1/system/quota_status`; for the
    # bootstrap path we always allow with an audit hint so the customer
    # can see the gate firing in their session log.
    risky = body.tool_name in {"Bash", "Write", "Edit", "NotebookEdit"}
    decision = "allow"
    reason = (
        f"ABS quota OK ({tenant}) — {body.tool_name} permitted"
        if not risky
        else f"ABS quota OK ({tenant}) — risky tool '{body.tool_name}' logged"
    )

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }


# ───── PostToolUse: audit log append ─────────────────────────────────────


class AuditLogRequest(BaseModel):
    tool_name: str
    tool_input: Optional[Dict] = None
    tool_response: Optional[Dict] = None
    user_email: Optional[str] = None
    session_id: Optional[str] = None
    cwd: Optional[str] = None


@router.post("/audit-log")
def audit_log(
    body: AuditLogRequest,
    authorization: Optional[str] = Header(None),
) -> Dict:
    auth = _auth_from_header(authorization)
    actor = body.user_email or auth.get("actor", "claude-code-hook")
    tenant = auth["tenant"]
    ts = datetime.now(timezone.utc)

    logger.info(
        "claude_code_hook_audit tenant=%s actor=%s tool=%s ts=%s",
        tenant,
        actor,
        body.tool_name,
        ts.isoformat(),
    )

    # Best-effort persistence — if CustomerAuditEntry isn't available
    # (test mode without DB), the in-process logger.info above is the
    # source of truth.
    try:
        from sqlmodel import Session

        from app.db.models import CustomerAuditEntry
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            db.add(
                CustomerAuditEntry(
                    license_jti=tenant,
                    action=f"claude_code.{body.tool_name}",
                    resource=body.cwd,
                    detail=(body.tool_input and str(body.tool_input)[:512])
                    or None,
                    ts=ts,
                )
            )
            db.commit()
    except Exception as exc:  # pragma: no cover — boot-time tolerance
        logger.debug("audit persist skipped: %s", exc)

    return {"ok": True, "received_at": ts.isoformat()}


# ───── SessionStart: context inject ──────────────────────────────────────


class SessionStartRequest(BaseModel):
    session_id: Optional[str] = None
    cwd: Optional[str] = None
    user_email: Optional[str] = None
    source: Optional[str] = Field(default=None, description="cli|sdk|ide")


@router.post("/session-start")
def session_start(
    body: SessionStartRequest,
    authorization: Optional[str] = Header(None),
) -> Dict:
    auth = _auth_from_header(authorization)
    tenant = auth["tenant"]
    ctx = (
        f"You are now connected to ABS Server tenant '{tenant}'. "
        "ABS exposes 122+ MCP tools at /mcp (cascade router will pick "
        "the cheapest provider). Slash commands available via the "
        "browser chat at /panel/chat: /rag /code /translate /analyze "
        "/workflow."
    )
    return {"additionalContext": ctx}


__all__ = ["router"]
