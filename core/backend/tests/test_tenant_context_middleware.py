# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""TenantContextMiddleware unit tests (SQLite default lane).

Guards the keystone that activates Postgres RLS: the pure-ASGI middleware
must pin the resolved tenant to ``current_tenant`` for the request and reset
it afterwards so a pooled connection cannot bleed a slug into the next
request. The DB-tier policy enforcement itself is covered by the
``postgres_only`` suite (test_rls_tenant_tables.py); here we only assert the
ContextVar lifecycle + resolver fail-open, which run anywhere.
"""

from __future__ import annotations

from starlette.requests import Request

from app.db.session import current_tenant
from app.middleware.tenant_context import (
    TenantContextMiddleware,
    resolve_request_tenant,
)


def _http_scope(headers: list | None = None) -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
    }


async def _recv() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(_message) -> None:  # pragma: no cover — sink
    return None


def test_resolver_fail_open_without_auth() -> None:
    """No bearer / no cookie → None (GUC stays unset = RLS fail-closed)."""
    assert resolve_request_tenant(Request(_http_scope())) is None


def test_resolver_ignores_garbage_bearer() -> None:
    headers = [(b"authorization", b"Bearer not-a-real-jwt")]
    assert resolve_request_tenant(Request(_http_scope(headers))) is None


async def test_middleware_sets_and_resets_contextvar(monkeypatch) -> None:
    seen: dict[str, str | None] = {}

    async def inner(scope, receive, send) -> None:
        seen["tenant"] = current_tenant.get()

    monkeypatch.setattr(
        "app.middleware.tenant_context.resolve_request_tenant",
        lambda request: "tenant_x",
    )
    mw = TenantContextMiddleware(inner)

    assert current_tenant.get() is None
    await mw(_http_scope(), _recv, _send)

    # Endpoint saw the pinned tenant …
    assert seen["tenant"] == "tenant_x"
    # … and it is reset on the way out (no pooled-connection bleed).
    assert current_tenant.get() is None


async def test_middleware_noop_when_unresolved(monkeypatch) -> None:
    seen: dict[str, str | None] = {}

    async def inner(scope, receive, send) -> None:
        seen["tenant"] = current_tenant.get()

    monkeypatch.setattr(
        "app.middleware.tenant_context.resolve_request_tenant",
        lambda request: None,
    )
    mw = TenantContextMiddleware(inner)
    await mw(_http_scope(), _recv, _send)

    assert seen["tenant"] is None
    assert current_tenant.get() is None


async def test_middleware_resets_even_on_endpoint_error(monkeypatch) -> None:
    async def boom(scope, receive, send) -> None:
        raise RuntimeError("endpoint blew up")

    monkeypatch.setattr(
        "app.middleware.tenant_context.resolve_request_tenant",
        lambda request: "tenant_x",
    )
    mw = TenantContextMiddleware(boom)
    try:
        await mw(_http_scope(), _recv, _send)
    except RuntimeError:
        pass
    # finally-block reset must run even when the endpoint raised.
    assert current_tenant.get() is None


async def test_middleware_passes_through_non_http() -> None:
    called: dict[str, bool] = {}

    async def inner(scope, receive, send) -> None:
        called["ok"] = True

    mw = TenantContextMiddleware(inner)
    await mw({"type": "lifespan"}, _recv, _send)
    assert called.get("ok") is True


# ── MCP transport → RLS ContextVar bridge ──────────────────────────────────


async def test_mcp_transport_bridges_tenant_to_rls(monkeypatch) -> None:
    """A valid abs_mcp_ token pins its tenant to current_tenant for the call.

    The /mcp transport is a mounted sub-app authenticated by an abs_mcp_ token
    (not an OAuth JWT TenantContextMiddleware can read), so the bridge lives in
    McpTokenAuthASGI. Without it the 120 MCP tools' DB access would run with no
    RLS scope on Postgres.
    """
    from app.config import settings as _settings
    from app.mcp.transport_auth import McpTokenAuthASGI

    monkeypatch.setattr(_settings, "mcp_auth_enforce", True, raising=False)
    monkeypatch.setattr(
        "app.api.mcp_tokens.verify_token",
        lambda _t: {"scope": "all", "tenant": "tenant_x", "actor": "u@x.io"},
    )

    seen: dict[str, str | None] = {}

    async def inner(scope, receive, send) -> None:
        seen["tenant"] = current_tenant.get()

    mw = McpTokenAuthASGI(inner)
    scope = {"type": "http", "headers": [(b"authorization", b"Bearer abs_mcp_x")]}
    await mw(scope, _recv, _send)

    assert seen["tenant"] == "tenant_x"
    # Reset after the tool call so a reused context cannot bleed the slug.
    assert current_tenant.get() is None


async def test_mcp_transport_no_tenant_claim_sets_no_guc(monkeypatch) -> None:
    """A token without a tenant claim leaves the GUC unset (fail-closed)."""
    from app.config import settings as _settings
    from app.mcp.transport_auth import McpTokenAuthASGI

    monkeypatch.setattr(_settings, "mcp_auth_enforce", True, raising=False)
    monkeypatch.setattr(
        "app.api.mcp_tokens.verify_token",
        lambda _t: {"scope": "all", "actor": "u@x.io"},
    )

    seen: dict[str, str | None] = {}

    async def inner(scope, receive, send) -> None:
        seen["tenant"] = current_tenant.get()

    mw = McpTokenAuthASGI(inner)
    scope = {"type": "http", "headers": [(b"authorization", b"Bearer abs_mcp_x")]}
    await mw(scope, _recv, _send)

    assert seen["tenant"] is None
    assert current_tenant.get() is None
