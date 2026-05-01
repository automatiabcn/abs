"""RAG indexer + query — Ollama erişimi yokken monkeypatch ile fake embed."""

from __future__ import annotations

import asyncio
import random

import pytest

pytest.importorskip("chromadb")

from app.config import settings
from app.rag import embedding as emb_mod
from app.rag import indexer
from app.rag.query import query as rag_query_fn
from app.rag.query import status as rag_status_fn


@pytest.fixture(autouse=True)
def _tmp_data(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))


@pytest.fixture
def fake_embed(monkeypatch):
    """768-dim deterministik fake embed (text → seed)."""

    async def _fake(text: str, *, timeout: float = 15.0):
        rnd = random.Random(hash(text) & 0xFFFF)
        return [rnd.random() for _ in range(768)]

    monkeypatch.setattr(emb_mod, "embed", _fake)
    return _fake


@pytest.mark.asyncio
async def test_index_path_indexes_three_md_files(fake_embed, tmp_path):
    proj = tmp_path / "demo"
    proj.mkdir()
    (proj / "a.md").write_text("# A\n" + "ABS RAG hakkında bir not. " * 20)
    (proj / "b.md").write_text("# B\n" + "Workflow durability paragraf. " * 20)
    (proj / "c.md").write_text("# C\n" + "Cohere alert pipeline yorumu. " * 20)

    res = await indexer.index_path(str(proj), project="t1")
    assert res["scanned_files"] == 3
    assert res["indexed"] >= 3
    assert res["skipped"] == 0


@pytest.mark.asyncio
async def test_query_returns_snippet(fake_embed, tmp_path):
    proj = tmp_path / "demo"
    proj.mkdir()
    (proj / "x.md").write_text("Workflow durability paragraf metni. " * 50)
    await indexer.index_path(str(proj), project="t1")
    hits = await rag_query_fn("workflow durability", project_filter="t1", top_k=3)
    assert len(hits) >= 1
    assert "snippet" in hits[0]
    assert hits[0]["project"] == "t1"


def test_status_after_index(fake_embed, tmp_path):
    proj = tmp_path / "demo"
    proj.mkdir()
    (proj / "y.md").write_text("Status testi" * 100)
    asyncio.run(indexer.index_path(str(proj), project="t2"))

    s = rag_status_fn()
    assert s["total_chunks"] >= 1
    assert s["embedding_model"] == "nomic-embed-text"


@pytest.mark.asyncio
async def test_clear_project_removes_only_that_project(fake_embed, tmp_path):
    p1 = tmp_path / "p1"
    p1.mkdir()
    (p1 / "a.md").write_text("project one " * 50)
    p2 = tmp_path / "p2"
    p2.mkdir()
    (p2 / "b.md").write_text("project two " * 50)
    await indexer.index_path(str(p1), project="proj_a")
    await indexer.index_path(str(p2), project="proj_b")

    res = indexer.clear(project="proj_a")
    assert res["deleted"] >= 1
    assert res["project"] == "proj_a"
    hits = await rag_query_fn("project", project_filter="proj_b", top_k=3)
    assert any("snippet" in h for h in hits)
