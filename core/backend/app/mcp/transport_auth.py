# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Bearer-token enforcement for the /mcp streamable-HTTP transport.

The FastMCP streamable-http app ships no authentication of its own, and the
``abs_mcp_`` tokens minted by ``POST /v1/mcp/tokens`` were never wired into
the transport — so any caller that passed the Host allowlist could list and
call all tools without a credential, spending the operator's provider keys.

This is a *pure ASGI* middleware (NOT Starlette ``BaseHTTPMiddleware``): the
MCP transport streams responses (SSE), and BaseHTTPMiddleware buffers the body
which would break the stream. We only inspect request headers before handing
off to the inner app, so streaming is untouched.

Enforcement is gated by ``settings.mcp_auth_enforce`` (default True). When the
header is missing or ``verify_token`` rejects it, we return a JSON-RPC-shaped
401 without ever touching the FastMCP session manager.
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class McpTokenAuthASGI:
    """Wrap the mounted /mcp ASGI app and require a valid abs_mcp_ token."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        # Only HTTP requests carry auth; lifespan/websocket pass straight through.
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # Re-read the toggle per request so it can be flipped without a rebuild
        # in dev; the import is local to avoid a settings import at module load.
        try:
            from app.config import settings

            enforce = bool(getattr(settings, "mcp_auth_enforce", True))
        except Exception:  # pragma: no cover — boot before settings load
            enforce = True

        if not enforce:
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in (scope.get("headers") or [])
        }
        auth = headers.get("authorization", "")
        token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""

        ok = False
        reason = "missing_token"
        mcp_tenant: str | None = None
        if token:
            try:
                from app.api.mcp_tokens import verify_token

                payload = verify_token(token)
                # Enforce token scope: only "mcp" / "all" tokens may drive the
                # MCP transport. A "hooks"-scoped token (issued for the hook
                # endpoints) must not be able to call the 122 tools here.
                tok_scope = str(payload.get("scope", "all"))
                if tok_scope not in ("mcp", "all"):
                    reason = f"scope_not_allowed:{tok_scope}"
                else:
                    # MT Phase 1 (W3) — stash the caller so MCP tools can apply
                    # per-owner (BYOK) provider keys to delegated LLM calls.
                    from app.mcp.context import set_mcp_caller

                    set_mcp_caller(payload.get("tenant"), payload.get("actor"))
                    mcp_tenant = str(payload.get("tenant") or "").strip() or None
                    ok = True
            except Exception as exc:  # HTTPException(401) or any decode error
                reason = getattr(exc, "detail", None) or "invalid_token"

        if not ok:
            response = JSONResponse(
                status_code=401,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32001,
                        "message": f"unauthorized: {reason}. Mint a token at "
                        "POST /v1/mcp/tokens and send it as 'Authorization: "
                        "Bearer abs_mcp_...'.",
                    },
                    "id": None,
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        # Bridge the MCP caller's tenant into the RLS ContextVar so
        # the Postgres RLS policies scope every DB access a tool makes. HTTP
        # routes get this from TenantContextMiddleware; the /mcp transport is a
        # mounted sub-app authenticated by an ``abs_mcp_`` token (not an OAuth
        # JWT the HTTP middleware can read), so the same ContextVar is pinned
        # here instead. Reset on the way out so a reused context cannot bleed
        # the slug into a later call. Inert on SQLite (listener no-ops).
        from app.db.session import current_tenant

        cv_token = current_tenant.set(mcp_tenant) if mcp_tenant else None
        try:
            await self.app(scope, receive, send)
        finally:
            if cv_token is not None:
                current_tenant.reset(cv_token)
