"""032 Modul I — `admin_overview` MCP tool.

MCP wrapper around the dashboard endpoint. Reads local data only — no live
external API calls. Intended for operator-side Claude Code usage.
"""

from __future__ import annotations

import json
from typing import List

REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


@mcp_server.tool()
@with_hooks("admin_overview")
async def admin_overview() -> str:
    """032 — Aggregated admin snapshot (billing/security/compliance/beta/vault)."""
    await tracker.bump("admin_overview")
    from app.api.admin.dashboard import _build_dashboard

    return json.dumps(await _build_dashboard(), indent=2, ensure_ascii=False, default=str)


REGISTERED_TOOLS.extend(["admin_overview"])
