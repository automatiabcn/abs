"""032 Modul I — admin_overview MCP tool."""

from __future__ import annotations

import asyncio
import json


def test_admin_overview_returns_aggregated_payload():
    from app.mcp.tools.admin_tools import admin_overview

    raw = asyncio.run(admin_overview())
    out = json.loads(raw)
    for key in ("billing", "beta", "compliance", "security", "vault"):
        assert key in out


def test_admin_overview_registered_in_server():
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert "admin_overview" in names
