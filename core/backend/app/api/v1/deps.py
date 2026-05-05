"""T-005 — MCP gateway shared FastAPI dependencies."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from cerbos.sdk.client import CerbosClient
from fastapi import Depends, Header, HTTPException, Request, status

from app.auth.cerbos_client import build_principal
from app.auth.oauth.server import OAuthError, verify_access_token
from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "AuthContext",
    "get_auth_context",
    "get_admin_or_bearer_auth_context",
    "get_cerbos_client",
]


@dataclass
class AuthContext:
    """Decoded principal context for the current request."""

    subject: str
    tenant_id: str | None
    roles: list[str]
    raw_claims: dict[str, Any]

    def as_principal(self):
        return build_principal(
            self.subject,
            roles=self.roles or ["member"],
            tenant_id=self.tenant_id,
        )


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="missing_bearer_token",
            headers={"WWW-Authenticate": 'Bearer realm="abs"'},
        )
    return authorization.split(" ", 1)[1].strip()


def get_auth_context(
    authorization: str | None = Header(default=None),
    x_abs_audience: str | None = Header(default=None),
) -> AuthContext:
    """Validate the Bearer JWT and surface principal claims."""
    token = _bearer_token(authorization)
    try:
        claims = verify_access_token(token, audience=x_abs_audience)
    except OAuthError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid_token: {exc.description}",
            headers={"WWW-Authenticate": 'Bearer realm="abs", error="invalid_token"'},
        ) from exc

    roles = claims.get("roles") or []
    if isinstance(roles, str):
        roles = [r.strip() for r in roles.split(",") if r.strip()]
    return AuthContext(
        subject=str(claims["sub"]),
        tenant_id=claims.get("tnt"),
        roles=list(roles),
        raw_claims=claims,
    )


# Founder Tester Round 2 (BUG-6) — `/admin/rag` console runs against
# `/v1/rag/*` which historically required a Bearer JWT. The single-tenant
# operator UX (cookie-based admin session) had no way to ship that token,
# so ingest/query 401'd. We expose a *secondary* dep that accepts either
# a Bearer JWT (multi-tenant API clients, MCP gateway, …) or the panel
# `abs_session` cookie (the operator console). The cookie path derives
# the admin's tenant from the users table and synthesises an AuthContext
# with `roles=["admin"]`. Bearer-only routes (hooks, audit log, MCP
# gateway) keep `get_auth_context` so their contract is unchanged.
def _admin_cookie_context(request: Request) -> AuthContext | None:
    """If the request carries a valid `abs_session` admin cookie, build
    an AuthContext from it. Returns `None` when no cookie is present or
    invalid so the caller can fall through to the Bearer error path."""
    from app.api.auth import COOKIE_NAME, _SessionExpired, _SessionInvalid, _decode_token

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        claims = _decode_token(token)
    except (_SessionExpired, _SessionInvalid):
        return None

    subject = str(claims.get("sub") or "")
    if not subject:
        return None

    try:
        from app.api.chat import _resolve_tenant

        tenant = _resolve_tenant(subject)
    except Exception:  # pragma: no cover — boot before users table
        tenant = "default"

    return AuthContext(
        subject=subject,
        tenant_id=tenant,
        roles=["admin"],
        raw_claims=dict(claims),
    )


def get_admin_or_bearer_auth_context(
    request: Request,
    authorization: str | None = Header(default=None),
    x_abs_audience: str | None = Header(default=None),
) -> AuthContext:
    """Bearer JWT preferred; falls back to the panel admin cookie session.

    Used by `/v1/rag/*` so the operator console can call ingest/query
    without minting a token by hand. Bearer wins when both are present so
    multi-tenant API clients keep their JWT semantics."""
    if authorization and authorization.lower().startswith("bearer "):
        return get_auth_context(
            authorization=authorization, x_abs_audience=x_abs_audience
        )

    cookie_ctx = _admin_cookie_context(request)
    if cookie_ctx is not None:
        return cookie_ctx

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="missing_bearer_token",
        headers={"WWW-Authenticate": 'Bearer realm="abs"'},
    )


def get_cerbos_client(request: Request) -> CerbosClient:
    """App-scoped singleton Cerbos client (initialized in lifespan)."""
    cli = getattr(request.app.state, "cerbos_client", None)
    if cli is None:
        cli = CerbosClient(settings.cerbos_host, timeout_secs=2.0)
        request.app.state.cerbos_client = cli
    return cli
