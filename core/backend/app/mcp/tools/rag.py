# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""RAG MCP tools — index, query, status, clear."""

from __future__ import annotations

import json
from typing import List, Optional

from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.rag import clear as _clear
from app.rag import index_path as _index_path
from app.rag import query as _query
from app.rag import status as _status

REGISTERED_TOOLS: List[str] = []


async def _query_qdrant_tenant(question: str, top_k: int) -> dict:
    """Search the panel-facing Qdrant document store for the configured tenant.

    Used when ABS_MCP_RAG_TENANT is set so files uploaded through the panel
    (/v1/rag/ingest) are answerable from Claude Code / Codex delegation. Runs
    the same embed → qc.search path the HTTP query endpoint uses, but scoped to
    settings.mcp_rag_tenant instead of a per-request auth claim.
    """
    import asyncio

    from app.rag import qdrant_client as qc
    from app.rag.embedding_bge import get_embedder

    tenant = settings.mcp_rag_tenant
    collection = settings.qdrant_default_collection

    def _run() -> dict:
        embedder = get_embedder()
        qc.ensure_collection(collection, vector_size=embedder.dim)
        vector = embedder.embed_one(question)
        hits = qc.search(
            collection=collection,
            tenant_id=tenant,
            query_vector=vector,
            limit=top_k,
        )
        return {
            "store": "qdrant",
            "tenant": tenant,
            "collection": collection,
            "count": len(hits),
            "results": [
                {
                    "score": h.get("score"),
                    "text": (h.get("payload") or {}).get("text", ""),
                    "metadata": {
                        k: v for k, v in (h.get("payload") or {}).items() if k != "text"
                    },
                }
                for h in hits
            ],
        }

    return await asyncio.to_thread(_run)


@mcp_server.tool()
@with_hooks("rag_index")
async def rag_index(
    path: str,
    project: str = "default",
    chunk_strategy: str = "semantic",
) -> str:
    """Add a file or directory to the RAG index. chunk_strategy: 'semantic' | 'char'."""
    await tracker.bump("rag_index")
    res = await _index_path(path, project=project, chunk_strategy=chunk_strategy)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("rag_query")
async def rag_query(
    question: str,
    project_filter: Optional[str] = None,
    top_k: int = 5,
) -> str:
    """Semantic search over the indexed chunks; returns the top_k nearest snippets.

    Two stores, one tool: with ABS_MCP_RAG_TENANT set it searches the documents
    uploaded through the panel (Qdrant); without it, the operator's local
    knowledge base (Chroma).
    """
    await tracker.bump("rag_query")
    if settings.mcp_rag_tenant:
        res = await _query_qdrant_tenant(question, top_k=top_k)
    else:
        res = await _query(question, project_filter=project_filter, top_k=top_k)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("rag_status")
async def rag_status() -> str:
    """RAG collection summary and disk usage."""
    await tracker.bump("rag_status")
    return json.dumps(_status(), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("rag_clear")
async def rag_clear(project: Optional[str] = None) -> str:
    """Delete the whole collection, or only the chunks of one project."""
    await tracker.bump("rag_clear")
    return json.dumps(_clear(project=project), ensure_ascii=False)


REGISTERED_TOOLS.extend(["rag_index", "rag_query", "rag_status", "rag_clear"])
