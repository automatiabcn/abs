"""Workflow durability MCP tool'ları — workflow_status (real) + workflow_resume."""

from __future__ import annotations

import json
from typing import List

from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.workflow import list_workflows, resume, stats

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("workflow_status")
async def workflow_status() -> str:
    """Workflow durability snapshot — toplam, by_status, son 5 + db_size_kb."""
    await tracker.bump("workflow_status")
    s = stats()
    s["active_workflows"] = list_workflows(limit=10, status="running")
    return json.dumps(s, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("workflow_resume")
async def workflow_resume(trace_id: str) -> str:
    """Bir workflow'un son başarılı adımdan devam state'ini döndür."""
    await tracker.bump("workflow_resume")
    return json.dumps(resume(trace_id), ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(["workflow_status", "workflow_resume"])
