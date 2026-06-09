# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sprint 2L — global tenant-context middleware (activates Postgres RLS).

Sprint 2K built the RLS plumbing — a ContextVar (``app.db.session.current_tenant``)
that a SQLAlchemy listener turns into ``SET LOCAL abs.tenant_id`` before every
Postgres cursor execute — but the dependency meant to populate it
(``app.api.v1.tenant_guc.set_request_tenant``) was never attached to a router.
So in the real request path the GUC stayed unset and the policies never
engaged; RLS only "worked" inside the dedicated ``postgres_only`` tests that
set the GUC by hand. This middleware closes that gap.

For every HTTP request it resolves the caller's tenant — Bearer JWT ``tnt``
claim first, else the panel ``abs_session`` admin cookie → users-table tenant —
and pins it to the ContextVar for the request's lifetime, resetting on the way
out so a pooled connection cannot bleed a slug into the next request.

Pure-ASGI (NOT ``BaseHTTPMiddleware``) on purpose: ``BaseHTTPMiddleware`` runs
the downstream app in a separate anyio task, so a ContextVar set in its
``dispatch`` does not reliably reach the endpoint / DB session. A pure-ASGI
middleware runs in the same task, so the value reaches the cursor-execute
listener.

Best-effort + fail-open: resolution never raises and never blocks a request —
authn/authz stay with the existing dependencies + Cerbos, and RLS is the third,
DB-tier safety net. On SQLite (self-host + the default test lane) the listener
is a no-op, so this middleware is inert there.
"""

from __future__ import annotations

import logging
from typing import Optional

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.db.session import current_tenant

logger = logging.getLogger(__name__)


def resolve_request_tenant(request: Request) -> Optional[str]:
    """Best-effort tenant slug from Bearer JWT or admin cookie. Never raises.

    Returns the slug or ``None`` (anonymous / public route / unresolved). A
    ``None`` result leaves the GUC unset, which RLS treats as fail-closed.
    """
    # 1) Bearer JWT ``tnt`` claim — multi-tenant API clients + MCP gateway.
    authz = request.headers.get("authorization")
    if authz and authz.lower().startswith("bearer "):
        try:
            from app.auth.oauth.server import verify_access_token

            claims = verify_access_token(
                authz.split(" ", 1)[1].strip(),
                audience=request.headers.get("x-abs-audience"),
            )
            tnt = str(claims.get("tnt") or "").strip()
            if tnt:
                return tnt
        except Exception:  # noqa: BLE001 — resolution must never block a request
            pass

    # 2) Panel ``abs_session`` admin cookie → users-table tenant (operator
    #    console UX, which does not mint a Bearer token by hand).
    try:
        from app.api.auth import COOKIE_NAME, _decode_token, _subject_revoked

        tok = request.cookies.get(COOKIE_NAME)
        if tok:
            claims = _decode_token(tok)
            sub = str(claims.get("sub") or "")
            if sub and not _subject_revoked(sub):
                from app.api.chat import _resolve_tenant

                tenant = str(_resolve_tenant(sub) or "").strip()
                if tenant:
                    return tenant
    except Exception:  # noqa: BLE001 — cookie path is best-effort
        pass

    return None


class TenantContextMiddleware:
    """Pin the request's tenant to ``current_tenant`` for RLS (pure ASGI)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        tenant = resolve_request_tenant(Request(scope))
        token = current_tenant.set(tenant) if tenant else None
        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                current_tenant.reset(token)


def install_tenant_context(app) -> None:
    """Attach the tenant-context middleware. Call once from app factory."""
    app.add_middleware(TenantContextMiddleware)
