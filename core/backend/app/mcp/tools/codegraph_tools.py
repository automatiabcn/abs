# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Code-graph MCP tools — deterministic blast-radius / callers / related.

Read-only over the caller's scoped graph (built with code_graph_build). No LLM,
no hallucination — the "what breaks if I change X?" answer a vector index cannot
give. Storage is per-caller: the graph key is the caller's tenant (hosted) or
the default local workspace.
"""

from __future__ import annotations

import json
from typing import List

from app.codegraph import graph as _graph
from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


def _caller_key() -> str:
    """Storage key for the current caller AND the project they have open.

    Keyed by tenant alone until 2026-08-03, so one developer's two projects
    shared a graph: index A, open B, and blast-radius answered about A with no
    sign that it had. The founder's rule after the first tester's feedback is
    that a capability works against the project in front of you — which means
    it also has to stop working against the one you closed.

    Adding the project to the key means an existing index is not found under
    the new key, so the first query after this ships reports nothing until the
    project is indexed again. That is the honest failure: an empty answer about
    the right project beats a full one about the wrong project.
    """
    tenant = "default"
    try:
        from app.mcp.context import get_mcp_caller

        caller_tenant, _user = get_mcp_caller()
        if caller_tenant:
            tenant = str(caller_tenant)
    except Exception:
        tenant = getattr(settings, "mcp_rag_tenant", None) or "default"

    try:
        import hashlib

        from app.mcp.context import get_mcp_caller
        from app.workspace.current import current_workspace

        _t, user = get_mcp_caller()
        root = current_workspace(tenant, user or "")
        if root:
            # Hashed, not appended: a storage key made of a customer's
            # directory layout ends up in logs and on disk.
            digest = hashlib.sha256(root.encode("utf-8")).hexdigest()[:12]
            return f"{tenant}:{digest}"
    except Exception:  # noqa: BLE001 — no workspace is a usable state
        pass
    return tenant


@mcp_server.tool()
@with_hooks("code_graph_build")
async def code_graph_build(root: str) -> str:
    """Index a workspace root into the call-graph (run before querying it)."""
    await tracker.bump("code_graph_build")
    res = _graph.build(root, key=_caller_key())
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("code_blast_radius")
async def code_blast_radius(target: str, max_hops: int = 3) -> str:
    """What breaks if `target` (symbol name or file path) changes — its transitive callers."""
    await tracker.bump("code_blast_radius")
    res = _graph.blast_radius(target, key=_caller_key(), max_hops=max_hops)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("code_callers")
async def code_callers(symbol: str) -> str:
    """Direct callers of a symbol."""
    await tracker.bump("code_callers")
    res = _graph.callers(symbol, key=_caller_key())
    return json.dumps({"symbol": symbol, "callers": res}, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("graph_related")
async def graph_related(symbol: str, depth: int = 1) -> str:
    """Symbols related to `symbol` within N hops (callers + callees, undirected)."""
    await tracker.bump("graph_related")
    res = _graph.graph_related(symbol, key=_caller_key(), depth=depth)
    return json.dumps(res, ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(
    ["code_graph_build", "code_blast_radius", "code_callers", "graph_related"]
)
