"""RAG MCP tool'ları (009): index, query, status, clear."""

from __future__ import annotations

import json
from typing import List, Optional

from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.rag import clear as _clear
from app.rag import index_path as _index_path
from app.rag import query as _query
from app.rag import status as _status

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("rag_index")
async def rag_index(
    path: str,
    project: str = "default",
    chunk_strategy: str = "semantic",
) -> str:
    """Bir dosya/dizini RAG index'ine ekle. chunk_strategy: 'semantic' | 'char'."""
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
    """Index'lenmiş chunk'larda anlam bazlı arama; en yakın top_k snippet döner."""
    await tracker.bump("rag_query")
    res = await _query(question, project_filter=project_filter, top_k=top_k)
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("rag_status")
async def rag_status() -> str:
    """RAG koleksiyon ve disk kullanım özeti."""
    await tracker.bump("rag_status")
    return json.dumps(_status(), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("rag_clear")
async def rag_clear(project: Optional[str] = None) -> str:
    """Tüm koleksiyonu veya yalnızca bir project'in chunk'larını sil."""
    await tracker.bump("rag_clear")
    return json.dumps(_clear(project=project), ensure_ascii=False)


REGISTERED_TOOLS.extend(["rag_index", "rag_query", "rag_status", "rag_clear"])
