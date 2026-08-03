# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Innovation MCP tools (symbol_search + rag_hybrid + judge_persona_predict)."""

from __future__ import annotations

import json
from typing import List, Optional

from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("symbol_search")
async def symbol_search(q: str, kind: Optional[str] = None, limit: int = 20) -> str:
    """Symbol DB substring search — name LIKE %q%, opsiyonel kind=function|class|import."""
    await tracker.bump("symbol_search")
    from app.symbols.store import search
    from app.workspace.current import current_workspace

    # Only this project's symbols. Without it the panel answered from every
    # repository the server had ever seen, and a hit gave no clue which.
    from app.mcp.context import get_mcp_caller

    try:
        tenant, user = get_mcp_caller()
    except Exception:  # noqa: BLE001 — no caller context is a usable state
        tenant, user = "default", ""
    root = current_workspace(str(tenant or "default"), str(user or ""))

    return json.dumps(
        {
            "query": q,
            "kind": kind,
            "scope": root or "everything indexed (no project open)",
            "results": search(q, limit=limit, kind=kind, under=root),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp_server.tool()
@with_hooks("rag_hybrid")
async def rag_hybrid(
    question: str,
    project_filter: Optional[str] = None,
    top_k: int = 5,
    alpha_semantic: float = 0.6,
) -> str:
    """RAG hybrid retrieval — BM25 + cosine fusion. alpha_semantic 0=BM25, 1=cosine."""
    await tracker.bump("rag_hybrid")
    from app.rag.hybrid import query_hybrid

    res = await query_hybrid(
        question,
        project_filter=project_filter,
        top_k=top_k,
        alpha_semantic=alpha_semantic,
    )
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("judge_persona_predict")
async def judge_persona_predict(
    ast_score: float, llm_score: float, persona_drift: float
) -> str:
    """predict the acceptance probability of these scores with an ML model."""
    await tracker.bump("judge_persona_predict")
    from app.judge.ml_persona import predict_accept

    return json.dumps(
        predict_accept(ast_score, llm_score, persona_drift),
        ensure_ascii=False,
        indent=2,
    )


REGISTERED_TOOLS.extend(["symbol_search", "rag_hybrid", "judge_persona_predict"])
