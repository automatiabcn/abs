# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""022 — Setup wizard funnel MCP tool: drop-off oranı her adım için."""

from __future__ import annotations

import json
from typing import List

REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


@mcp_server.tool()
@with_hooks("wizard_funnel")
async def wizard_funnel() -> str:
    """022 — Setup wizard 6-adım drop-off özeti."""
    await tracker.bump("wizard_funnel")
    from app.wizard.metrics import funnel_summary

    return json.dumps(funnel_summary(), ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(["wizard_funnel"])
