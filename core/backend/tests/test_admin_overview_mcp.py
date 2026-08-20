"""admin_overview MCP tool."""

from __future__ import annotations

import asyncio
import json


def test_admin_overview_returns_aggregated_payload():
    from app.mcp.tools.admin_tools import admin_overview

    # admin_overview reads the whole server and is operator-only since the
    # 2026-08-18 scope fix. With an operator identity it returns the payload;
    # a non-operator token is refused (its own test elsewhere).
    from app.mcp.context import mcp_user_subject
    from app.config import settings as _s

    _s_admin = _s.admin_email
    _s.admin_email = "owner@abs.local"
    tok = mcp_user_subject.set("owner@abs.local")
    try:
        raw = asyncio.run(admin_overview())
    finally:
        mcp_user_subject.reset(tok)
        _s.admin_email = _s_admin
    out = json.loads(raw)
    assert out.get("error") != "operator_only", out
    for key in ("billing", "beta", "compliance", "security", "vault"):
        assert key in out


def test_admin_overview_registered_in_server():
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert "admin_overview" in names
