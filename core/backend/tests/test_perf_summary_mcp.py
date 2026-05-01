"""021 — perf_summary MCP tool: response shape."""

from __future__ import annotations

import asyncio
import json


def test_perf_summary_response_shape():
    from app.mcp.tools.perf_tools import perf_summary

    raw = asyncio.run(perf_summary())
    out = json.loads(raw)
    for key in ("cascade", "vault", "symbol", "watchdog", "last_run", "results_dir"):
        assert key in out, f"perf_summary missing key: {key}"
