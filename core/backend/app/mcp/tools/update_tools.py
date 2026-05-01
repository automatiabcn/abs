"""014 — Update / health / breaker MCP tool'lari (3 tool)."""

from __future__ import annotations

import json
from typing import List

from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("update_check")
async def update_check() -> str:
    """Remote release manifest → version compare → state JSON."""
    await tracker.bump("update_check")
    from app.main import app as fastapi_app
    from app.update.manifest import fetch_manifest, update_state

    manifest = await fetch_manifest()
    return json.dumps(
        update_state(manifest, fastapi_app.version),
        ensure_ascii=False,
        indent=2,
    )


@mcp_server.tool()
@with_hooks("health_status")
async def health_status() -> str:
    """Tum provider'larin real-time ping durumu."""
    await tracker.bump("health_status")
    from app.health.monitor import monitor

    return json.dumps(
        {"providers": monitor.snapshot()}, ensure_ascii=False, indent=2
    )


@mcp_server.tool()
@with_hooks("breaker_status")
async def breaker_status() -> str:
    """Cascade circuit breaker state'leri (open/half_open/closed)."""
    await tracker.bump("breaker_status")
    from app.cascade.breaker import default_breaker

    return json.dumps(
        {"states": default_breaker.snapshot()},
        ensure_ascii=False,
        indent=2,
        default=str,
    )


REGISTERED_TOOLS.extend(["update_check", "health_status", "breaker_status"])
