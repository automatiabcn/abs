"""Q8 Phase P — Claude Code lifecycle hook receivers.

Three webhook endpoints the customer's `~/.claude/settings.json` can
point at so their Claude Code session is gated by ABS:

  POST /v1/hooks/quota-check    — PreToolUse: budget gate
  POST /v1/hooks/audit-log      — PostToolUse: append to audit
  POST /v1/hooks/session-start  — SessionStart: tenant context inject

All three accept the integration token issued by `/v1/mcp/tokens`
(scope=hooks or all). Token is HMAC-signed; no DB lookup needed.

Q10-L6-001 — quota-check now enforces a soft per-tenant rolling-hour
counter on risky tools (Bash/Write/Edit/NotebookEdit) instead of
unconditionally returning "allow". Production deployments should swap
the in-process counter for Redis (cluster-safe).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.mcp_tokens import verify_token


def _auth_dependency(
    authorization: Optional[str] = Header(None),
) -> Dict:
    """Q11-L15-001: enforce auth at the dependency layer so the 401
    fires BEFORE pydantic body validation. Previously the routes took
    `authorization: Header(None)` as a regular parameter; FastAPI
    parses the body first, returning 422 to unauthed callers and
    leaking the request schema. Declared as `dependencies=[...]` on
    the router so every hook endpoint inherits the gate."""
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


router = APIRouter(
    prefix="/v1/hooks",
    tags=["claude-code-hooks"],
    dependencies=[Depends(_auth_dependency)],
)
logger = logging.getLogger(__name__)


def _auth_from_header(authorization: Optional[str]) -> Dict:
    """Retained for the per-route handlers that need the decoded
    payload. Same logic as the router-level dependency; both are safe
    to call (idempotent verify)."""
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


RISKY_TOOLS = {"Bash", "Write", "Edit", "NotebookEdit"}
RISKY_HOURLY_LIMIT = 100

# Tenant → deque of UNIX timestamps for risky-tool invocations within the
# last 3600 s. Lock prevents lost updates under uvicorn workers > 1; for
# multi-replica deployments swap with Redis (cluster-safe rolling window).
_risky_window: Dict[str, Deque[float]] = defaultdict(deque)
_risky_lock = threading.Lock()


def _record_and_count(tenant: str) -> int:
    """Insert a now-timestamp, drop entries older than 1h, return count."""
    cutoff = time.time() - 3600
    with _risky_lock:
        bucket = _risky_window[tenant]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        bucket.append(time.time())
        return len(bucket)


@router.post("/quota-check")
def quota_check(
    body: QuotaCheckRequest,
    authorization: Optional[str] = Header(None),
) -> Dict:
    auth = _auth_from_header(authorization)
    tenant = auth["tenant"]

    if body.tool_name not in RISKY_TOOLS:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": (
                    f"ABS quota OK ({tenant}) — {body.tool_name} non-risky"
                ),
            }
        }

    used = _record_and_count(tenant)
    if used > RISKY_HOURLY_LIMIT:
        # Q10-L6-001 — hard gate so a runaway Claude Code session can't
        # burn unbounded risky operations against a single tenant.
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"ABS quota exceeded ({tenant}): {used} risky calls in "
                    f"last hour > {RISKY_HOURLY_LIMIT}. Wait or contact "
                    "operator."
                ),
            }
        }
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": (
                f"ABS quota OK ({tenant}) — risky tool '{body.tool_name}'"
                f" accepted ({used}/{RISKY_HOURLY_LIMIT} this hour)"
            ),
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
