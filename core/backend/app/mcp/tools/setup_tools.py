# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""MCP tool for reading the setup wizard's current state."""

from __future__ import annotations

import json
from typing import List

from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("setup_status")
async def setup_status() -> str:
    """Current state of the install wizard, as JSON."""
    await tracker.bump("setup_status")
    from app.api.setup import read_state

    return json.dumps(read_state(), ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(["setup_status"])
