# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""MCP tools that report where the licence and the demo period stand."""

from __future__ import annotations

import json
from typing import List

from app.config import settings
from app.licensing.demo import status as demo_status_fn
from app.mcp.gate import _gate_status
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("license_status")
async def license_status() -> str:
    """Licence and demo status, as JSON."""
    await tracker.bump("license_status")
    g = _gate_status()
    d = demo_status_fn()
    return json.dumps(
        {
            "license_active": g["license_active"],
            "demo": d,
            "require_license": settings.mcp_require_license,
            "allowed": g["allowed"],
            "purchase_url": "https://abs.automatiabcn.com/",
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp_server.tool()
@with_hooks("demo_status")
async def demo_status() -> str:
    """Demo countdown durum (started/expired/days_remaining)."""
    await tracker.bump("demo_status")
    return json.dumps(demo_status_fn(), ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(["license_status", "demo_status"])
