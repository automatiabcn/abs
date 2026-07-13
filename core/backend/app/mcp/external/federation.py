# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Federate a tenant's external MCP tools into ABS's own MCP surface.

Two consumers:

  * ``/mcp`` re-expose — register each discovered upstream tool into the shared
    FastMCP server as ``ext_<slug>__<tool>`` so the operator's connected Claude
    Code / Codex sees it. The FastMCP instance is GLOBAL (tools are not
    per-session), so this is gated behind ``external_mcp_federate_to_mcp`` and is
    only tenant-safe on a single-tenant deployment (a self-host box, tenant=default).

  * server-side agents — ``call_federated`` lets an agent invoke an external
    tool with an explicit tenant, so agent use stays tenant-scoped even when the
    /mcp re-expose is off.

The proxy is a ``Tool`` subclass whose ``run`` forwards the raw arguments to the
upstream MCP client (bypassing FastMCP's signature validation, since upstream
schemas are dynamic) while still advertising the upstream ``inputSchema`` via the
overridden ``parameters`` field.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import PrivateAttr

from app.config import settings
from app.mcp.external import client as ext_client
from app.mcp.external import service

logger = logging.getLogger(__name__)

# slug -> list of federated FastMCP tool names (for clean unregister).
_FEDERATED: dict[str, list[str]] = {}

_NAME_RE = re.compile(r"[^a-zA-Z0-9_]+")


def _safe(part: str) -> str:
    return _NAME_RE.sub("_", part).strip("_")


def federated_name(slug: str, tool_name: str) -> str:
    return f"ext_{_safe(slug)}__{_safe(tool_name)}"[:128]


async def _noop() -> str:  # pragma: no cover — only feeds Tool.from_function
    """external MCP proxy"""
    return ""


def _make_proxy_tool(
    ext_name: str,
    description: str,
    schema: dict,
    tenant_slug: str,
    slug: str,
    orig: str,
):
    """Build a FastMCP Tool that proxies to the upstream server on call.

    The proxy stores only (tenant_slug, slug, orig) — NOT the decrypted secret.
    The connection (and its token) is re-resolved from the encrypted row at call
    time, so a rotated/cleared secret takes effect immediately and the plaintext
    token never lingers in the long-lived Tool object.
    """
    from mcp.server.fastmcp.tools.base import Tool

    class _ProxyTool(Tool):
        _tenant: str = PrivateAttr(default="")
        _slug: str = PrivateAttr(default="")
        _orig: str = PrivateAttr(default="")

        async def run(self, arguments, context=None, convert_result=False):  # type: ignore[override]
            from mcp.types import TextContent

            # The FastMCP registry is global, so every tenant's federated
            # proxies are visible to every authenticated MCP caller. Pin each
            # proxy to its owning tenant: a caller whose resolved tenant
            # differs from this tool's tenant cannot reach the upstream (and
            # its credentials). "_global" = no tenant context (internal/admin
            # token) and is allowed, matching prior behaviour.
            from app.mcp.context import get_mcp_caller

            caller_tenant, _ = get_mcp_caller()
            if caller_tenant != "_global" and caller_tenant != self._tenant:
                return [
                    TextContent(
                        type="text",
                        text="[external MCP tool: cross-tenant access denied]",
                    )
                ]

            conn = service.connection_params(self._tenant, self._slug)
            if not conn or not conn.get("enabled"):
                return [
                    TextContent(type="text", text="[external MCP server unavailable]")
                ]
            try:
                res = await ext_client.call_external_tool(
                    conn["url"],
                    conn["transport"],
                    conn.get("headers") or {},
                    self._orig,
                    arguments or {},
                )
                if res.get("ok"):
                    text = res.get("text") or ""
                else:
                    text = f"[external tool error] {res.get('text') or res.get('is_error')}"
            except ext_client.ExternalMcpError as exc:
                text = f"[external MCP error] {exc}"
            return [TextContent(type="text", text=text)]

    # structured_output=False — the proxy returns plain TextContent (the
    # upstream's serialised result), so the tool must NOT advertise an
    # outputSchema or FastMCP rejects the unstructured proxy response.
    tool = _ProxyTool.from_function(
        _noop, name=ext_name, description=description, structured_output=False
    )
    # Advertise the upstream schema instead of the no-arg _noop signature.
    if isinstance(schema, dict) and schema:
        tool.parameters = schema
    tool._tenant = tenant_slug
    tool._slug = slug
    tool._orig = orig
    return tool


async def federate_server(tenant_slug: str, slug: str) -> int:
    """(Re)register one server's tools into the shared /mcp. Returns tool count."""
    if not getattr(settings, "external_mcp_federate_to_mcp", False):
        return 0
    conn = service.connection_params(tenant_slug, slug)
    if not conn or not conn.get("enabled"):
        unfederate_server(slug)
        return 0

    try:
        tools = await ext_client.discover_tools(
            conn["url"], conn["transport"], conn.get("headers") or {}
        )
    except ext_client.ExternalMcpError as exc:
        logger.warning("federate_discover_failed slug=%s: %s", slug, exc)
        return 0

    from app.mcp.server import mcp_server

    unfederate_server(slug)  # drop any stale proxies first
    registered: list[str] = []
    for t in tools:
        ext_name = federated_name(slug, t.name)
        proxy = _make_proxy_tool(
            ext_name, t.description, t.input_schema, tenant_slug, slug, t.name
        )
        mcp_server._tool_manager._tools[ext_name] = proxy
        registered.append(ext_name)
    _FEDERATED[slug] = registered
    logger.info(
        "federated slug=%s tools=%d tenant=%s", slug, len(registered), tenant_slug
    )
    return len(registered)


def unfederate_server(slug: str) -> int:
    """Remove a server's proxy tools from the shared /mcp. Returns count removed."""
    names = _FEDERATED.pop(slug, [])
    if not names:
        return 0
    from app.mcp.server import mcp_server

    for name in names:
        try:
            mcp_server._tool_manager.remove_tool(name)
        except Exception:  # already gone — best effort
            pass
    logger.info("unfederated slug=%s tools=%d", slug, len(names))
    return len(names)


async def refresh_federation() -> int:
    """Startup hook — rebuild the /mcp federation from all enabled servers."""
    if not getattr(settings, "external_mcp_federate_to_mcp", False):
        return 0
    total = 0
    for entry in service.list_enabled_for_federation():
        total += await federate_server(entry["tenant_slug"], entry["slug"])
    return total


def federated_overview() -> dict:
    """Diagnostics — how many proxy tools are live, by server slug."""
    return {
        "enabled": bool(getattr(settings, "external_mcp_federate_to_mcp", False)),
        "servers": {slug: len(names) for slug, names in _FEDERATED.items()},
        "total_tools": sum(len(n) for n in _FEDERATED.values()),
    }


# ── Agent-facing (tenant-scoped, independent of the /mcp re-expose) ──────────


async def call_federated(
    tenant_slug: str, slug: str, tool_name: str, arguments: Optional[dict] = None
) -> dict:
    """Invoke an external tool for a specific tenant (server-side agent use)."""
    conn = service.connection_params(tenant_slug, slug)
    if not conn:
        return {"ok": False, "text": "not_found"}
    if not conn.get("enabled"):
        return {"ok": False, "text": "disabled"}
    return await ext_client.call_external_tool(
        conn["url"],
        conn["transport"],
        conn.get("headers") or {},
        tool_name,
        arguments or {},
    )
