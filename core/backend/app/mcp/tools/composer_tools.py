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


def _caller() -> tuple[str, str | None]:
    """(tenant, user) for this call. BOTH halves matter, for different reasons.

    The tenant keys the symbol graph — per workspace, so two developers in one
    tenant do not each re-index the same repository.

    The user is where the customer's provider keys are filed (`owner_type =
    'user'`). Dropping it — which this function used to do, with a variable
    named `_user` — meant `tenant_configured_providers` found nothing and the
    Composer built its chain from the OPERATOR's keys alone. Measured on
    08-02: an account with five keys ran eight tasks and exactly one provider
    was attempted, the operator's, while `capability_status` on the same token
    reported five. The customer's keys were invisible to the feature they
    bought.
    """
    try:
        from app.mcp.context import get_mcp_caller

        tenant, user = get_mcp_caller()
        if tenant:
            return str(tenant), (str(user) if user else None)
    except Exception:  # noqa: BLE001 — an unknown caller is the operator's own
        pass
    return (getattr(settings, "mcp_rag_tenant", None) or "default"), None


@mcp_server.tool()
@with_hooks("composer_propose")
async def composer_propose(task: str, workspace_root: str) -> str:
    """Propose a multi-file edit for `task`, graded + blast-annotated, applied to nothing.

    Each edit carries a Senior-Judge score, a code-graph blast-radius, and a
    dry-run verdict; `risk`/`requires_approval` are derived from those. Apply
    approved edits with the patch tools.
    """
    await tracker.bump("composer_propose")
    import json as _json

    from app.composer import run_composer
    from app.workspace.current import problem_with_root

    bad = problem_with_root(workspace_root)
    if bad:
        return _json.dumps({"error": bad}, ensure_ascii=False)

    tenant, user = _caller()
    # The project's key, not the tenant's. This read `graph_key=tenant` under a
    # comment saying "the graph is per workspace" — true when it was written,
    # and false from 2026-08-03, when the graph moved to a per-project key
    # because one developer's two projects were answering about each other.
    # That fix reached codegraph_tools and stopped there, so Composer's
    # blast-radius badge — what a developer reads before approving a deletion —
    # was still looking in a bucket the editor's index command never fills.
    from app.mcp.tools.codegraph_tools import _key_for

    run = await run_composer(
        task,
        workspace_root=workspace_root,
        tenant_id=tenant,
        user_subject=user,
        graph_key=_key_for(tenant, workspace_root),
    )
    return run.model_dump_json(indent=2)


REGISTERED_TOOLS.extend(["composer_propose"])
