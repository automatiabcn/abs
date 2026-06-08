# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Outbound MCP client — connect to a tenant's external MCP server.

ABS is itself an MCP *server* (``app/mcp/server.py``); this module is the
inverse: an MCP *client* that reaches a third-party server the tenant added.

SECURITY — the URL is operator-supplied, so the connection is a classic SSRF
vector (an admin could point it at ``http://169.254.169.254/`` or an internal
service and have the server fetch it). ``_assert_safe_url`` therefore:

  * allows only ``http`` / ``https`` schemes,
  * resolves the host and REJECTS any address that lands in a loopback /
    private / link-local / reserved / multicast range unless
    ``settings.external_mcp_allow_private`` is explicitly on (local dogfood),
  * is re-checked at call time (not just at add time) so DNS-rebinding between
    "test connection" and a later tool call cannot smuggle an internal target.

All calls are time-boxed and the discovered tool list is capped.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

from app.config import settings


class ExternalMcpError(Exception):
    """Raised for any outbound-MCP failure (validation, connect, call)."""


# A federated tool's description is forwarded verbatim to the operator's Claude
# client — a malicious upstream could embed prompt-injection there. Strip
# control chars and hard-cap the length before it ever leaves this module.
_MAX_DESC = 500
_MAX_RESULT_CHARS = 200_000  # ~200 KB — a runaway upstream cannot flood callers


def sanitize_description(text: str) -> str:
    text = text or ""
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 0x20)
    return text[:_MAX_DESC]


@dataclass(frozen=True)
class ExternalTool:
    name: str
    description: str
    input_schema: dict


def _assert_safe_url(url: str) -> None:
    """Reject malformed URLs and (unless allowed) internal/private targets."""
    try:
        parsed = urlparse(url)
    except Exception as exc:  # pragma: no cover — urlparse is very lenient
        raise ExternalMcpError(f"invalid_url: {exc}") from exc

    if parsed.scheme not in ("http", "https"):
        raise ExternalMcpError("invalid_scheme: only http/https allowed")
    host = parsed.hostname
    if not host:
        raise ExternalMcpError("invalid_url: missing host")

    if getattr(settings, "external_mcp_allow_private", False):
        return  # dev / dogfood — caller has opted into reaching localhost

    # Resolve every address the host maps to; a single private hit is fatal.
    try:
        infos = socket.getaddrinfo(host, parsed.port or 0, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ExternalMcpError(f"dns_resolution_failed: {host}") from exc

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ExternalMcpError(
                f"blocked_internal_address: {host} -> {addr} "
                "(set ABS_EXTERNAL_MCP_ALLOW_PRIVATE=true only on an isolated dev box)"
            )


def build_headers(auth_type: str, secret: str, header_name: str = "") -> dict:
    """Translate the stored auth config into outbound request headers."""
    if auth_type == "bearer" and secret:
        return {"Authorization": f"Bearer {secret}"}
    if auth_type == "header" and secret and header_name:
        return {header_name: secret}
    return {}


def _client_ctx(url: str, transport: str, headers: dict):
    """Return the async-context-manager for the chosen transport.

    Uses the ``headers=`` form of the transport clients (verified against the
    server's mcp 1.27.x). The streamable-http ``streamablehttp_client`` is
    marked deprecated in favour of ``streamable_http_client(http_client=...)``,
    but the new form takes a pre-built httpx client instead of headers; we keep
    the proven headers= path and will migrate if/when the old name is removed.
    """
    timeout = float(getattr(settings, "external_mcp_timeout_seconds", 20.0))
    if transport == "sse":
        from mcp.client.sse import sse_client

        return sse_client(url, headers=headers, timeout=timeout)
    # default: streamable-http
    from mcp.client.streamable_http import streamablehttp_client  # noqa: deprecation

    return streamablehttp_client(url, headers=headers, timeout=timeout)


async def _with_session(url: str, transport: str, headers: dict, fn):
    """Open transport + MCP session, run ``fn(session)``, always tear down."""
    import asyncio

    from mcp import ClientSession

    timeout = float(getattr(settings, "external_mcp_timeout_seconds", 20.0))

    async def _run() -> Any:
        ctx = _client_ctx(url, transport, headers)
        async with ctx as streams:
            # streamable-http yields (read, write, get_session_id); sse yields
            # (read, write). Take the first two either way.
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)

    try:
        return await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise ExternalMcpError(f"timeout after {timeout:.0f}s") from exc
    except ExternalMcpError:
        raise
    except Exception as exc:  # connect refused, protocol error, auth 401, …
        raise ExternalMcpError(f"{type(exc).__name__}: {exc}") from exc


async def discover_tools(
    url: str, transport: str, headers: Optional[dict] = None
) -> list[ExternalTool]:
    """Connect, run tools/list, return the (capped) discovered tools."""
    _assert_safe_url(url)
    headers = headers or {}
    cap = int(getattr(settings, "external_mcp_max_tools", 200))

    async def _list(session) -> list[ExternalTool]:
        res = await session.list_tools()
        out: list[ExternalTool] = []
        for t in res.tools[:cap]:
            out.append(
                ExternalTool(
                    name=t.name,
                    description=sanitize_description(t.description or ""),
                    input_schema=getattr(t, "inputSchema", None) or {},
                )
            )
        return out

    return await _with_session(url, transport, headers, _list)


async def call_external_tool(
    url: str,
    transport: str,
    headers: Optional[dict],
    tool_name: str,
    arguments: dict,
) -> dict:
    """Connect and invoke a single tool; return {ok, text, is_error}."""
    _assert_safe_url(url)
    headers = headers or {}

    async def _call(session) -> dict:
        res = await session.call_tool(tool_name, arguments or {})
        text = ""
        for block in (res.content or []):
            text += getattr(block, "text", "") or ""
            if len(text) >= _MAX_RESULT_CHARS:
                text = text[:_MAX_RESULT_CHARS] + "\n…[truncated]"
                break
        return {"ok": not res.isError, "is_error": bool(res.isError), "text": text}

    return await _with_session(url, transport, headers, _call)
