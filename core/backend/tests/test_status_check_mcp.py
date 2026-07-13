"""025 Modul F — `status_check` MCP tool."""

from __future__ import annotations

import asyncio
import json


def test_status_check_response_shape():
    from app.mcp.tools.status_tools import status_check

    raw = asyncio.run(status_check())
    out = json.loads(raw)
    for key in (
        "uptime_seconds",
        "timestamp",
        "services",
        "overall",
        "licenses",
        "revenue_today_usd",
        "recent_errors",
    ):
        assert key in out, f"missing key: {key}"
    assert isinstance(out["services"], list)
    assert out["overall"] in {"ok", "degraded", "down", "unknown"}
    assert "active" in out["licenses"]


def test_status_check_revenue_uses_today_window():
    from app.mcp.tools.status_tools import status_check

    raw = asyncio.run(status_check())
    out = json.loads(raw)
    assert isinstance(out["revenue_today_usd"], (int, float))
    assert out["revenue_today_usd"] >= 0
