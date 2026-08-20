"""The knowledge base is per tenant. A's rag_clear does not touch B's chunks;
A's rag_query does not read them.

Audit 2026-08-18: the RAG MCP tools scoped by a server-wide setting and
otherwise not at all — one Chroma collection, `project` metadata only.
"""

from __future__ import annotations

import json

import pytest

import importlib

from app.rag import indexer

q = importlib.import_module("app.rag.query")


class _Coll:
    """Enough of a Chroma collection to test scoping without Chroma."""

    def __init__(self):
        self.rows = {}  # id -> (doc, meta)
        self.name = "abs_default"

    def add(self, ids, documents, embeddings, metadatas):
        for i, d, m in zip(ids, documents, metadatas):
            self.rows[i] = (d, dict(m))

    def count(self):
        return len(self.rows)

    @staticmethod
    def _match(meta, where):
        if not where:
            return True
        if "$and" in where:
            return all(_Coll._match(meta, w) for w in where["$and"])
        return all(meta.get(k) == v for k, v in where.items())

    def get(self, where=None, include=None, limit=None, offset=0):
        ids = [i for i, (_d, m) in self.rows.items() if self._match(m, where)]
        ids = ids[offset:] if offset else ids
        if limit:
            ids = ids[:limit]
        return {"ids": ids, "metadatas": [self.rows[i][1] for i in ids]}

    def update(self, ids, metadatas):
        for i, m in zip(ids, metadatas):
            self.rows[i] = (self.rows[i][0], dict(m))

    def delete(self, where=None):
        for i in [i for i, (_d, m) in self.rows.items() if self._match(m, where)]:
            del self.rows[i]

    def query(self, query_embeddings, n_results, where=None):
        ids = [i for i, (_d, m) in self.rows.items() if self._match(m, where)][:n_results]
        return {
            "documents": [[self.rows[i][0] for i in ids]],
            "metadatas": [[self.rows[i][1] for i in ids]],
            "distances": [[0.1 for _ in ids]],
            "ids": [ids],
        }


@pytest.fixture
def coll(monkeypatch):
    c = _Coll()
    monkeypatch.setattr(indexer, "_collection", lambda name="abs_default": c)
    monkeypatch.setattr(q, "_collection", lambda name="abs_default": c)

    async def fake_embed(text):
        return [0.0, 1.0]

    monkeypatch.setattr(q._emb, "embed", fake_embed)
    # seed: two tenants, one legacy chunk with no owner
    c.add(["a1"], ["alpha doc"], [[0, 1]], [{"project": "p", "tenant": "acme", "file": "a.md"}])
    c.add(["b1"], ["beta doc"], [[0, 1]], [{"project": "p", "tenant": "globex", "file": "b.md"}])
    c.add(["l1"], ["legacy doc"], [[0, 1]], [{"project": "p", "file": "l.md"}])
    return c


def test_scope_where_shapes():
    assert indexer.scope_where(None, None) is None
    assert indexer.scope_where("acme", None) == {"tenant": "acme"}
    assert indexer.scope_where(None, "p") == {"project": "p"}
    assert indexer.scope_where("acme", "p") == {"$and": [{"tenant": "acme"}, {"project": "p"}]}


@pytest.mark.asyncio
async def test_a_tenant_reads_only_its_own_chunks(coll):
    hits = await q.query("x", tenant="acme")
    assert [h["file"] for h in hits] == ["a.md"]
    hits = await q.query("x", tenant="globex")
    assert [h["file"] for h in hits] == ["b.md"]


def test_a_tenant_clears_only_its_own_chunks(coll):
    out = indexer.clear(tenant="acme")
    assert out["deleted"] == 1
    assert set(coll.rows) == {"b1", "l1"}
    # and cannot drop the collection by leaving project empty
    assert "b1" in coll.rows


def test_status_counts_the_tenants_chunks_not_the_servers(coll, monkeypatch):
    class _Client:
        def list_collections(self):
            return [coll]

    monkeypatch.setattr(q, "_client", lambda: _Client())
    monkeypatch.setattr(q.settings, "data_dir", "/nonexistent", raising=False)
    assert q.status(tenant="acme")["total_chunks"] == 1
    assert q.status()["total_chunks"] == 3


def test_legacy_chunks_are_assigned_once_to_the_default_tenant(coll):
    n = indexer.backfill_tenant()
    assert n == 1
    assert coll.rows["l1"][1]["tenant"] == indexer.LEGACY_TENANT
    assert indexer.backfill_tenant() == 0  # idempotent


@pytest.mark.asyncio
async def test_the_mcp_tools_scope_by_the_calling_token(coll, monkeypatch):
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import rag as rt

    monkeypatch.setattr(rt, "_caller_tenant", lambda: "acme")
    monkeypatch.setattr(rt.settings, "mcp_rag_tenant", "", raising=False)
    hits = json.loads(await rt.rag_query("x"))
    assert [h["file"] for h in hits] == ["a.md"]
    out = json.loads(await rt.rag_clear())
    assert out["deleted"] == 1 and set(coll.rows) == {"b1", "l1"}


def test_index_path_stamps_the_owner(tmp_path, monkeypatch, coll):
    import asyncio

    (tmp_path / "doc.md").write_text("hello world " * 20)

    async def fake_embed(text):
        return [0.0, 1.0]

    monkeypatch.setattr(indexer, "_embed_one", fake_embed)
    res = asyncio.run(indexer.index_path(str(tmp_path), project="p", tenant="acme"))
    assert res["indexed"] >= 1
    stamped = [m for _d, m in coll.rows.values() if m.get("file", "").endswith("doc.md")]
    assert stamped and all(m["tenant"] == "acme" for m in stamped)
