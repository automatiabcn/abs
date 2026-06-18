# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

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
from sqlmodel import select

from app.api.auth import current_admin
from app.api.chat import _resolve_tenant
from app.config import settings
from app.db.models import MintedTokenBlacklist, MintedTokenRecord
from app.db.session import get_session_sync


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


def _token_digest(token: str) -> str:
    """Q10-L6-002 — stable digest for blacklist storage (not the raw token)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_revoked(token: str) -> bool:
    digest = _token_digest(token)
    with get_session_sync() as db:
        row = db.exec(
            select(MintedTokenBlacklist).where(
                MintedTokenBlacklist.token_digest == digest
            )
        ).first()
        return row is not None


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
    if _is_revoked(token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token_revoked")
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
    # Record issuance (digest only — never the raw token) so the panel can list
    # and individually revoke multiple active tokens. Best-effort: a ledger
    # failure must not block handing the operator their token.
    try:
        with get_session_sync() as db:
            db.add(MintedTokenRecord(
                token_digest=_token_digest(token), tenant_slug=tenant,
                label=body.label, scope=body.scope, issued_by=admin["sub"],
                issued_at=issued_at, expires_at=expires_at,
            ))
            db.commit()
    except Exception:  # noqa: BLE001 — ledger is best-effort
        logger.info("mcp_token issuance-ledger write skipped", exc_info=True)
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


class RevokeTokenRequest(BaseModel):
    # Revoke by raw token (legacy / paste) OR by digest. The raw token is shown
    # only once at mint, so the panel's multi-token list revokes by digest.
    token: Optional[str] = Field(default=None, min_length=16)
    token_digest: Optional[str] = Field(default=None, min_length=16, max_length=64)
    reason: Optional[str] = Field(default=None, max_length=256)


class RevokedTokenInfo(BaseModel):
    token_digest: str
    tenant_slug: str
    label: str
    revoked_by: str
    revoked_at: datetime
    expires_at: Optional[datetime]
    reason: Optional[str]


@router.post("/tokens/revoke", status_code=204)
def revoke_token(
    body: RevokeTokenRequest, admin: dict = Depends(current_admin)
) -> None:
    """Q10-L6-002 — admin marks a previously-minted token as revoked.

    Idempotent: revoking an already-blacklisted token is a no-op.
    Decoding is best-effort; an unrecognised payload still gets recorded
    so a leaked token can be killed even if its body has drifted.
    """
    tenant = _resolve_tenant(admin["sub"])
    label = ""
    expires_at: Optional[datetime] = None
    if body.token:
        digest = _token_digest(body.token)
        try:
            payload = verify_token(body.token)
        except HTTPException:
            # token already invalid (expired/malformed) — still allow blacklist
            # under the admin's own tenant so the digest is logged for audit +
            # future regression checks.
            payload = None
        if payload is not None:
            # An admin may only revoke tokens minted for THEIR OWN tenant. The
            # old code overwrote `tenant` with the token's self-asserted claim,
            # so presenting another tenant's token blacklisted it under that
            # tenant's slug with this admin as `revoked_by` — a cross-tenant
            # isolation break. Reject the mismatch instead of trusting the claim.
            tok_tenant = str(payload.get("tenant", tenant))
            if tok_tenant != tenant:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, "cross_tenant_revoke_forbidden"
                )
            label = str(payload.get("label", ""))
            if "exp" in payload:
                expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    elif body.token_digest:
        # Panel list revoke: resolve metadata from this tenant's issuance ledger.
        digest = body.token_digest.strip()
        with get_session_sync() as db:
            rec = db.exec(
                select(MintedTokenRecord).where(
                    MintedTokenRecord.token_digest == digest,
                    MintedTokenRecord.tenant_slug == tenant,
                )
            ).first()
        if rec is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "token_not_found")
        label = rec.label
        expires_at = rec.expires_at
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "token_or_digest_required")

    with get_session_sync() as db:
        existing = db.exec(
            select(MintedTokenBlacklist).where(
                MintedTokenBlacklist.token_digest == digest
            )
        ).first()
        if existing is not None:
            return None
        entry = MintedTokenBlacklist(
            token_digest=digest,
            tenant_slug=tenant,
            label=label,
            revoked_by=admin["sub"],
            expires_at=expires_at,
            reason=body.reason,
        )
        db.add(entry)
        db.commit()
    logger.info(
        "mcp_token_revoked tenant=%s label=%s by=%s reason=%s",
        tenant,
        label,
        admin["sub"],
        body.reason or "",
    )
    return None


@router.get("/tokens/revoked", response_model=list[RevokedTokenInfo])
def list_revoked_tokens(
    admin: dict = Depends(current_admin),
) -> list[RevokedTokenInfo]:
    """Q10-L6-002 — list of revoked tokens for the admin's tenant."""
    tenant = _resolve_tenant(admin["sub"])
    with get_session_sync() as db:
        rows = db.exec(
            select(MintedTokenBlacklist)
            .where(MintedTokenBlacklist.tenant_slug == tenant)
            .order_by(MintedTokenBlacklist.revoked_at.desc())  # type: ignore[attr-defined]
        ).all()
    return [
        RevokedTokenInfo(
            token_digest=r.token_digest,
            tenant_slug=r.tenant_slug,
            label=r.label,
            revoked_by=r.revoked_by,
            revoked_at=r.revoked_at,
            expires_at=r.expires_at,
            reason=r.reason,
        )
        for r in rows
    ]


class ActiveTokenInfo(BaseModel):
    token_digest: str
    label: str
    scope: str
    issued_by: str
    issued_at: datetime
    expires_at: Optional[datetime]
    status: str  # "active" | "revoked" | "expired"


@router.get("/tokens", response_model=list[ActiveTokenInfo])
def list_tokens(admin: dict = Depends(current_admin)) -> list[ActiveTokenInfo]:
    """Issued MCP tokens for the admin's tenant (newest first), each with a
    derived status. Lets the operator manage MULTIPLE tokens — the raw token is
    only shown once at mint, so the list keys off the digest for revoke."""
    tenant = _resolve_tenant(admin["sub"])
    now = datetime.now(timezone.utc)
    with get_session_sync() as db:
        rows = db.exec(
            select(MintedTokenRecord)
            .where(MintedTokenRecord.tenant_slug == tenant)
            .order_by(MintedTokenRecord.issued_at.desc())  # type: ignore[attr-defined]
        ).all()
        revoked = {
            r.token_digest for r in db.exec(
                select(MintedTokenBlacklist).where(
                    MintedTokenBlacklist.tenant_slug == tenant
                )
            ).all()
        }
    out: list[ActiveTokenInfo] = []
    for r in rows:
        # SQLite returns tz-naive datetimes; treat them as UTC so the comparison
        # with the tz-aware `now` doesn't raise (and doesn't 500 the list).
        exp = r.expires_at
        if exp is not None and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if r.token_digest in revoked:
            st = "revoked"
        elif exp is not None and exp <= now:
            st = "expired"
        else:
            st = "active"
        out.append(ActiveTokenInfo(
            token_digest=r.token_digest, label=r.label, scope=r.scope,
            issued_by=r.issued_by, issued_at=r.issued_at,
            expires_at=r.expires_at, status=st,
        ))
    return out


__all__ = [
    "router",
    "verify_token",
    "MintTokenRequest",
    "MintedToken",
    "RevokeTokenRequest",
    "RevokedTokenInfo",
    "ActiveTokenInfo",
]
