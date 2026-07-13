# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Smart link MCP tools.

  smart_link_status() — list connected services + last validation
  provider_validate(provider, api_key) — provider validators wrapper
"""

from __future__ import annotations

import json
from typing import List

REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


@mcp_server.tool()
@with_hooks("smart_link_status")
async def smart_link_status() -> str:
    """026 — Connected services list + last validation status."""
    await tracker.bump("smart_link_status")
    from app.smart_link.vault_secrets import list_secrets

    return json.dumps(
        {"connected": list_secrets(), "count": len(list_secrets())},
        ensure_ascii=False,
        indent=2,
    )


@mcp_server.tool()
@with_hooks("provider_validate")
async def provider_validate(provider: str, api_key: str) -> str:
    """026 — Validate provider API key (live test call)."""
    await tracker.bump("provider_validate")
    from app.smart_link.provider_validators import validate

    return json.dumps(
        validate(provider, api_key), ensure_ascii=False, indent=2
    )


REGISTERED_TOOLS.extend(["smart_link_status", "provider_validate"])
