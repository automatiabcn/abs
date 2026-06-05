# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""MCP rag_query store selection — Chroma (default) vs Qdrant (tenant-scoped).

When ABS_MCP_RAG_TENANT is set, the MCP rag_query tool must search the
panel-facing Qdrant document store for THAT tenant (so panel uploads are
answerable from Claude Code / Codex). When empty, it must keep using the
operator Chroma KB — no behaviour change, no cross-tenant leak.
"""

from __future__ import annotations

import asyncio
import json

import pytest

import app.mcp.server  # noqa: F401  — ensure full tool registration before importing the tool module directly
from app.config import settings
from app.mcp.tools import rag as rag_tool
from app.rag import embedding_bge, qdrant_client as qc


class _StubEmbedder:
    dim = 1024

    def embed_one(self, text: str):
        return [0.1] * self.dim


def test_rag_query_uses_chroma_when_tenant_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mcp_rag_tenant", "", raising=False)
    called = {}

    async def _fake_query(question, project_filter=None, top_k=5):
        called["chroma"] = (question, top_k)
        return {"store": "chroma", "results": []}

    monkeypatch.setattr(rag_tool, "_query", _fake_query)

    out = json.loads(asyncio.run(rag_tool.rag_query("hello", top_k=3)))
    assert out["store"] == "chroma"
    assert called["chroma"] == ("hello", 3)


def test_rag_query_searches_qdrant_when_tenant_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mcp_rag_tenant", "digisfer", raising=False)
    monkeypatch.setattr(settings, "qdrant_default_collection", "abs_documents", raising=False)
    monkeypatch.setattr(embedding_bge, "get_embedder", lambda: _StubEmbedder())
    monkeypatch.setattr(qc, "ensure_collection", lambda *a, **k: None)

    captured = {}

    def _fake_search(*, collection, tenant_id, query_vector, limit, **kw):
        captured.update(collection=collection, tenant_id=tenant_id, limit=limit)
        return [
            {
                "id": "doc-1",
                "score": 0.91,
                "payload": {"text": "rent due on the 5th", "doc_id": "lease.pdf"},
            }
        ]

    monkeypatch.setattr(qc, "search", _fake_search)

    out = json.loads(asyncio.run(rag_tool.rag_query("when is rent due", top_k=4)))
    assert out["store"] == "qdrant"
    assert out["tenant"] == "digisfer"
    assert captured == {"collection": "abs_documents", "tenant_id": "digisfer", "limit": 4}
    assert out["count"] == 1
    hit = out["results"][0]
    assert hit["text"] == "rent due on the 5th"
    assert hit["metadata"]["doc_id"] == "lease.pdf"
    assert "text" not in hit["metadata"]
