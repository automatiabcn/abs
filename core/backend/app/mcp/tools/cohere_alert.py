# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Cohere quota alert MCP tool'ları (009).

008 STUB `cohere_alert_status` workflow_stub.py'den taşındı; gerçek implementasyon
`app.cohere.alert` modülünden besleniyor.
"""

from __future__ import annotations

import json
from typing import List

from app.cohere import mark_acknowledged, read_recent, usage_snapshot
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("cohere_alert_status")
async def cohere_alert_status() -> str:
    """Cohere kullanım + son alert + severity (ok|warn|danger|limit_hit)."""
    await tracker.bump("cohere_alert_status")
    return json.dumps(usage_snapshot(), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("cohere_alerts_recent")
async def cohere_alerts_recent(limit: int = 10) -> str:
    """Son N alert kaydı (en yeni önce)."""
    await tracker.bump("cohere_alerts_recent")
    return json.dumps(read_recent(limit=limit), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("cohere_alert_ack")
async def cohere_alert_ack(alert_id: str) -> str:
    """Bir alert'i acknowledge işaretle."""
    await tracker.bump("cohere_alert_ack")
    ok = mark_acknowledged(alert_id)
    return json.dumps({"ok": ok, "alert_id": alert_id})


REGISTERED_TOOLS.extend(
    ["cohere_alert_status", "cohere_alerts_recent", "cohere_alert_ack"]
)
