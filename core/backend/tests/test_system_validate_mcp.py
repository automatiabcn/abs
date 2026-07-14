"""system_validate MCP tool."""

from __future__ import annotations

import asyncio
import json


def test_system_validate_returns_results_shape():
    from app.mcp.tools.validate_tools import _CACHE, system_validate

    _CACHE["data"] = None
    _CACHE["ts"] = 0.0
    raw = asyncio.run(system_validate(force=True))
    out = json.loads(raw)
    assert "results" in out
    assert "ok" in out


def test_system_validate_cache_returns_same_object_within_ttl():
    from app.mcp.tools.validate_tools import _CACHE, system_validate

    _CACHE["data"] = None
    _CACHE["ts"] = 0.0
    raw1 = asyncio.run(system_validate(force=True))
    # Cache should now be populated; second call (no force) hits cache
    raw2 = asyncio.run(system_validate(force=False))
    assert raw1 == raw2
