"""Q8 Phase N + P — MCP integration tokens.

Issues short-lived bearer tokens that the customer's Claude Code (or
any external MCP client) attaches to:

  * `${ABS}/mcp` — JSON-RPC tool/resource bridge (already mounted by
    `app/mcp/server.py` in `app.main`); this module supplies the auth
    token rotation surface.

  * `${ABS}/v1/hooks/*` — Claude Code lifecycle hooks (Phase P), so the
    same token gates `quota-check`, `audit-log`, and `session-start`.

The token is HMAC-signed with the panel session secret so we don't need
a new database column. Tenant is encoded into the payload, scope
limits which subsystems honour the token, and a 90-day default expiry
keeps blast radius bounded.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.auth import current_admin
from app.api.chat import _resolve_tenant
from app.config import settings


router = APIRouter(prefix="/v1/mcp", tags=["mcp"])
logger = logging.getLogger(__name__)


TokenScope = Literal["mcp", "hooks", "all"]


class MintTokenRequest(BaseModel):
    label: str = Field(..., min_length=2, max_length=64)
    scope: TokenScope = "all"
    ttl_days: int = Field(default=90, ge=1, le=365)


class MintedToken(BaseModel):
    token: str
    label: str
    scope: TokenScope
    tenant_slug: str
    expires_at: datetime


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload: Dict) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    sig = hmac.new(
        settings.session_secret.encode("utf-8"), body, hashlib.sha256
    ).digest()
    return f"abs_mcp_{_b64url(body)}.{_b64url(sig)}"


def verify_token(token: str) -> Dict:
    """Decode + HMAC verify. Returns payload on success."""
    if not token.startswith("abs_mcp_"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token_prefix")
    rest = token[len("abs_mcp_"):]
    try:
        body_b64, sig_b64 = rest.split(".", 1)
        body = _b64url_decode(body_b64)
        provided = _b64url_decode(sig_b64)
    except (ValueError, IndexError) as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "malformed_token"
        ) from exc

    expected = hmac.new(
        settings.session_secret.encode("utf-8"), body, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad_signature")

    payload: Dict = json.loads(body.decode("utf-8"))
    if payload.get("exp", 0) < time.time():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token_expired")
    return payload


@router.post("/tokens", response_model=MintedToken, status_code=201)
def mint_token(
    body: MintTokenRequest, admin: dict = Depends(current_admin)
) -> MintedToken:
    """Issue a fresh HMAC-signed integration token for the panel admin."""
    tenant = _resolve_tenant(admin["sub"])
    issued_at = datetime.now(timezone.utc)
    expires_ts = int(issued_at.timestamp()) + body.ttl_days * 86400
    expires_at = datetime.fromtimestamp(expires_ts, tz=timezone.utc)
    payload = {
        "v": 1,
        "tenant": tenant,
        "scope": body.scope,
        "label": body.label,
        "iat": int(issued_at.timestamp()),
        "exp": expires_ts,
        "actor": admin["sub"],
    }
    token = _sign(payload)
    logger.info(
        "mcp_token_issued tenant=%s scope=%s label=%s expires=%s",
        tenant,
        body.scope,
        body.label,
        expires_at.isoformat(),
    )
    return MintedToken(
        token=token,
        label=body.label,
        scope=body.scope,
        tenant_slug=tenant,
        expires_at=expires_at,
    )


@router.get("/tokens/verify")
def verify_endpoint(
    authorization: Optional[str] = Header(None),
) -> Dict:
    """Public endpoint — any caller with a token can confirm it's valid."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "missing_bearer_token"
        )
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_token(token)
    return {
        "ok": True,
        "tenant": payload.get("tenant"),
        "scope": payload.get("scope"),
        "label": payload.get("label"),
        "expires_at": datetime.fromtimestamp(
            payload["exp"], tz=timezone.utc
        ).isoformat(),
    }


__all__ = ["router", "verify_token", "MintTokenRequest", "MintedToken"]
