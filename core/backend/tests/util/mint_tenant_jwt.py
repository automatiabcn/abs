"""Phase 5 / Q2.CO2 — tenant JWT mint helper.

Tests need to call protected RAG endpoints (`/v1/rag/{ingest,query}`) which
require an OAuth bearer JWT signed with the same RSA private key the
production OAuth issuer uses. This helper short-circuits the
authorization-code dance for in-process / CI tests by signing a token
directly.

Usage::

    from tests.util.mint_tenant_jwt import mint
    token = mint(tenant_slug="tenant-acme", scopes=["rag:read", "rag:write"])
    headers = {"Authorization": f"Bearer {token}"}

The signed JWT carries the same `tnt` + `scope` claims the gateway expects
(see `app.auth.oauth.server.issue_access_token`). Default TTL is 1 hour.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import jwt as pyjwt

from app.config import settings
from app.licensing.keys import load_private_key


DEFAULT_AUDIENCE = "abs-mcp"
# Match production issuer (settings.oauth_issuer) so gateway middleware
# accepts test-minted tokens. Falls back to the same default the OAuth
# server uses when env override is unset.
DEFAULT_ISSUER = getattr(settings, "oauth_issuer", "https://abs.local")


def mint(
    tenant_slug: str,
    *,
    subject: str = "test-user",
    scopes: Optional[Iterable[str]] = None,
    audience: Optional[str] = None,
    ttl_seconds: int = 3600,
    extras: Optional[dict] = None,
) -> str:
    """Sign a tenant-scoped access token with the production RSA key.

    Args:
        tenant_slug: value placed in the `tnt` claim — equivalent to the
            tenants.slug column.
        subject: `sub` claim (defaults to `test-user`).
        scopes: list of OAuth scopes (defaults to `rag:read rag:write`).
        audience: optional `aud` claim. Default: omitted so gateway accepts
            the token without requiring an `X-Abs-Audience` header. Pass
            explicitly when the route under test asserts a specific audience.
        ttl_seconds: token lifetime in seconds.
        extras: additional claims merged into the payload (overwrites
            generated keys).

    Returns:
        Compact JWS string (RS256 signed).
    """
    issued_at = datetime.now(tz=timezone.utc)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    scope_list = list(scopes) if scopes else ["rag:read", "rag:write"]

    payload: dict[str, object] = {
        "iss": DEFAULT_ISSUER,
        "sub": subject,
        "tnt": tenant_slug,
        "scope": " ".join(scope_list),
        "scopes": scope_list,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if audience is not None:
        payload["aud"] = audience
    if extras:
        payload.update(extras)

    private_key_bytes = load_private_key(settings.private_key_path)
    return pyjwt.encode(payload, private_key_bytes, algorithm="RS256")


def authorization_header(tenant_slug: str, **kwargs: object) -> dict[str, str]:
    """Convenience: produce a `{"Authorization": "Bearer <jwt>"}` dict
    suitable for plugging straight into requests/httpx."""
    token = mint(tenant_slug, **kwargs)  # type: ignore[arg-type]
    return {"Authorization": f"Bearer {token}"}


__all__ = ["DEFAULT_AUDIENCE", "DEFAULT_ISSUER", "authorization_header", "mint"]
