# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""027 Modul F — `vault_audit_status` MCP tool."""

from __future__ import annotations

import json
from typing import List

REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


@mcp_server.tool()
@with_hooks("vault_audit_status")
async def vault_audit_status(limit: int = 50) -> str:
    """027 — Vault audit chain integrity + recent entries."""
    await tracker.bump("vault_audit_status")
    from app.vault.audit_chain import stats

    return json.dumps(stats(recent_limit=limit), ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(["vault_audit_status"])
