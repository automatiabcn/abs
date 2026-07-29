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
    """Storage key for the current caller (tenant), falling back to default."""
    try:
        from app.mcp.context import get_mcp_caller

        tenant, _user = get_mcp_caller()
        if tenant:
            return str(tenant)
    except Exception:
        pass
    return getattr(settings, "mcp_rag_tenant", None) or "default"


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
