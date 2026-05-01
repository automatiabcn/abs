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

__all__ = ["AuthContext", "get_auth_context", "get_cerbos_client"]


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


def get_cerbos_client(request: Request) -> CerbosClient:
    """App-scoped singleton Cerbos client (initialized in lifespan)."""
    cli = getattr(request.app.state, "cerbos_client", None)
    if cli is None:
        cli = CerbosClient(settings.cerbos_host, timeout_secs=2.0)
        request.app.state.cerbos_client = cli
    return cli
