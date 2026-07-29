# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Composer MCP tool — a pre-reviewed multi-file edit proposal over /mcp.

The editor calls this to get graded, blast-annotated diffs it can render and
gate on before applying (via patch_engine). Per-caller scoped.
"""

from __future__ import annotations

from typing import List

from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

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
@with_hooks("composer_propose")
async def composer_propose(task: str, workspace_root: str) -> str:
    """Propose a multi-file edit for `task`, graded + blast-annotated, applied to nothing.

    Each edit carries a Senior-Judge score, a code-graph blast-radius, and a
    dry-run verdict; `risk`/`requires_approval` are derived from those. Apply
    approved edits with the patch tools.
    """
    await tracker.bump("composer_propose")
    from app.composer import run_composer

    key = _caller_key()
    run = await run_composer(
        task,
        workspace_root=workspace_root,
        tenant_id=key,
        graph_key=key,
    )
    return run.model_dump_json(indent=2)


REGISTERED_TOOLS.extend(["composer_propose"])
