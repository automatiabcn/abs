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


def _key_for(tenant: str, root: str) -> str:
    """The storage key for one tenant's one project.

    Hashed rather than appended: a storage key made of a customer's directory
    layout ends up in logs and on disk.
    """
    import hashlib
    import os

    try:
        resolved = os.path.realpath(root)
    except OSError:
        resolved = root
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:12]
    return f"{tenant}:{digest}"


def _caller_key(workspace_root: str = "", client_id: str = "") -> str:
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
        from app.mcp.context import get_mcp_caller
        from app.workspace.current import current_workspace

        _t, user = get_mcp_caller()
        root = current_workspace(
            tenant, user or "", client_id=client_id, explicit_root=workspace_root
        )
        if root:
            # Hashed, not appended: a storage key made of a customer's
            # directory layout ends up in logs and on disk.
            return _key_for(tenant, root)
    except Exception:  # noqa: BLE001 — no workspace is a usable state
        pass
    return tenant


@mcp_server.tool()
@with_hooks("code_graph_build")
async def code_graph_build(root: str) -> str:
    """Index a workspace root into the call-graph (run before querying it)."""
    await tracker.bump("code_graph_build")
    from app.workspace.current import problem_with_root

    bad = problem_with_root(root)
    if bad:
        # Indexing the server's own directory is worse than not indexing at
        # all: every later blast-radius answer would be drawn from it, and
        # drawn confidently.
        return json.dumps({"error": bad}, ensure_ascii=False)

    # Keyed by the root being built, not by whichever workspace was announced.
    #
    # Those are the same in the normal flow, and silently different when
    # `workspace_set` failed — an older server, a path the container cannot
    # see. The graph would then be written under the tenant-only key while
    # every later query looked under tenant+project, so the project stayed
    # "not indexed" no matter how many times somebody indexed it.
    tenant = _caller_key().split(":", 1)[0]
    res = _graph.build(root, key=_key_for(tenant, root))

    # Building a graph for a root is a statement that you are working on it.
    #
    # Without this, a client that indexes and then queries — an older editor,
    # or any other MCP client that has never heard of `workspace_set` — wrote
    # the graph under the project key and read back under the tenant key, and
    # got nothing. The live transport test caught exactly that. An announced
    # workspace still wins: this only fills the gap, it never overrides.
    try:
        from app.mcp.context import get_mcp_caller
        from app.workspace.current import current_workspace, set_workspace

        _t, user = get_mcp_caller()
        if not current_workspace(tenant, str(user or "")):
            set_workspace(tenant, str(user or ""), root)
    except Exception:  # noqa: BLE001 — the graph is built either way
        pass

    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("code_blast_radius")
async def code_blast_radius(
    target: str, max_hops: int = 3, workspace_root: str = "", client_id: str = ""
) -> str:
    """What breaks if `target` (symbol name or file path) changes — its transitive callers."""
    await tracker.bump("code_blast_radius")
    res = _graph.blast_radius(
        target, key=_caller_key(workspace_root, client_id), max_hops=max_hops
    )
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("code_callers")
async def code_callers(symbol: str, workspace_root: str = "", client_id: str = "") -> str:
    """Direct callers of a symbol."""
    await tracker.bump("code_callers")
    res = _graph.callers(symbol, key=_caller_key(workspace_root, client_id))
    return json.dumps({"symbol": symbol, "callers": res}, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("graph_related")
async def graph_related(
    symbol: str, depth: int = 1, workspace_root: str = "", client_id: str = ""
) -> str:
    """Symbols related to `symbol` within N hops (callers + callees, undirected)."""
    await tracker.bump("graph_related")
    res = _graph.graph_related(
        symbol, key=_caller_key(workspace_root, client_id), depth=depth
    )
    return json.dumps(res, ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(
    ["code_graph_build", "code_blast_radius", "code_callers", "graph_related"]
)
