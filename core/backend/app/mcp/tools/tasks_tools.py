# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Tasks MCP tools — the meeting → task → code chain, readable from the editor.

Per-caller scoped (tenant → default), like notes. A task carries its origin
('manual', 'meeting:<id>', 'composer:<run_id>') and optionally the file it is
about — the trail is the feature, not the todo list.
"""

from __future__ import annotations

import json
from typing import List

from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.tasks_companion import service as _tasks

REGISTERED_TOOLS: List[str] = []


def _caller_key() -> str:
    try:
        from app.mcp.context import get_mcp_caller

        tenant, _user = get_mcp_caller()
        if tenant:
            return str(tenant)
    except Exception:
        pass
    return getattr(settings, "mcp_rag_tenant", None) or "default"


@mcp_server.tool()
@with_hooks("task_add")
async def task_add(
    title: str, body: str = "", source: str = "manual", file: str = "", project: str = ""
) -> str:
    """Create a task. ``source`` says where it came from — 'manual',
    'meeting:<id>' for a lifted action item, 'composer:<run_id>' for follow-up
    work an agent run left behind. ``file`` ties it to code when there is one."""
    await tracker.bump("task_add")
    res = _tasks.add(
        title,
        key=_caller_key(),
        body=body,
        source=source,
        file=file,
        project=project,
    )
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("task_list")
async def task_list(status: str = "open", limit: int = 100) -> str:
    """Tasks for this caller. ``status``: 'open' (default), 'done' or 'all'."""
    await tracker.bump("task_list")
    items = _tasks.list_tasks(key=_caller_key(), status=status, limit=limit)
    return json.dumps(
        {"ok": True, "tasks": items, "stats": _tasks.stats(key=_caller_key())},
        ensure_ascii=False,
        indent=2,
    )


@mcp_server.tool()
@with_hooks("task_done")
async def task_done(task_id: str, reopen: bool = False) -> str:
    """Mark a task done (or open again with reopen=true). A missing id is an
    error, never a silent success — that would read as work completed."""
    await tracker.bump("task_done")
    res = _tasks.set_status(
        task_id, "open" if reopen else "done", key=_caller_key()
    )
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("task_delete")
async def task_delete(task_id: str) -> str:
    """Delete a task."""
    await tracker.bump("task_delete")
    ok = _tasks.delete(task_id, key=_caller_key())
    return json.dumps({"ok": ok, "id": task_id}, ensure_ascii=False)


REGISTERED_TOOLS.extend(["task_add", "task_list", "task_done", "task_delete"])
