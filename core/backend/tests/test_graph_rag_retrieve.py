"""GraphRAG — hybrid retrieval unit tests (vector + Neo4j stubbed)."""

from __future__ import annotations

import pytest

from app.graph_rag import retrieve as rt


_HITS = [
    {
        "id": "c1",
        "score": 0.81,
        "payload": {
            "chunk_id": "c1",
            "doc_id": "doc1",
            "filename": "kira.docx",
            "text": "Ahmet, ABC şirketinde çalışıyor.",
        },
    },
    {
        "id": "c2",
        "score": 0.66,
        "payload": {
            "chunk_id": "c2",
            "doc_id": "doc1",
            "filename": "kira.docx",
            "text": "ABC İstanbul'da bulunuyor.",
        },
    },
]

_SUBGRAPH_ROWS = [
    {
        "src_id": "person:ahmet",
        "src_name": "Ahmet",
        "src_type": "Person",
        "rel_type": "WORKS_AT",
        "dst_id": "organization:abc",
        "dst_name": "ABC",
        "dst_type": "Organization",
    },
    {
        "src_id": "organization:abc",
        "src_name": "ABC",
        "src_type": "Organization",
        "rel_type": None,  # seed entity with no outgoing relation
        "dst_id": None,
        "dst_name": None,
        "dst_type": None,
    },
]


class _FakeNeo4j:
    def __init__(self, rows, fail=False) -> None:
        self._rows = rows
        self._fail = fail

    async def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        if self._fail:
            raise RuntimeError("neo4j down")
        return self._rows


@pytest.fixture
def _patch_vector(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rt, "_vector_search", lambda q, t, k: list(_HITS))
    yield


@pytest.mark.asyncio
async def test_query_assembles_citations_and_subgraph(
    monkeypatch: pytest.MonkeyPatch, _patch_vector
) -> None:
    async def _synth(prompt, tenant_id):
        # The prompt should carry both the chunks and the graph triples.
        assert "kira.docx" in prompt
        assert "WORKS_AT" in prompt
        return "Ahmet, ABC şirketinde çalışıyor [1]."

    monkeypatch.setattr(rt, "_synthesize", _synth)
    res = await rt.graph_rag_query(
        "Ahmet nerede çalışıyor?",
        tenant_id="t1",
        top_k=5,
        neo4j_client=_FakeNeo4j(_SUBGRAPH_ROWS),
    )
    assert res.answer.endswith("[1].")
    assert [c.chunk_id for c in res.citations] == ["c1", "c2"]
    assert res.citations[0].source == "kira.docx"
    assert {e["id"] for e in res.entities} == {"person:ahmet", "organization:abc"}
    assert len(res.relations) == 1
    assert res.relations[0]["type"] == "WORKS_AT"
    assert res.used_graph is True


@pytest.mark.asyncio
async def test_query_no_hits_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt, "_vector_search", lambda q, t, k: [])
    res = await rt.graph_rag_query(
        "boş", tenant_id="t1", neo4j_client=_FakeNeo4j([])
    )
    assert res.answer is None
    assert res.citations == []
    assert res.used_graph is False


@pytest.mark.asyncio
async def test_query_degrades_when_neo4j_down(
    monkeypatch: pytest.MonkeyPatch, _patch_vector
) -> None:
    async def _synth(prompt, tenant_id):
        return "chunks only [1]"

    monkeypatch.setattr(rt, "_synthesize", _synth)
    res = await rt.graph_rag_query(
        "soru", tenant_id="t1", neo4j_client=_FakeNeo4j([], fail=True)
    )
    # Still answers from chunks; graph is empty.
    assert res.answer == "chunks only [1]"
    assert len(res.citations) == 2
    assert res.entities == []
    assert res.used_graph is False


@pytest.mark.asyncio
async def test_query_without_synthesis_returns_retrieval_only(
    monkeypatch: pytest.MonkeyPatch, _patch_vector
) -> None:
    res = await rt.graph_rag_query(
        "soru",
        tenant_id="t1",
        synthesize=False,
        neo4j_client=_FakeNeo4j(_SUBGRAPH_ROWS),
    )
    assert res.answer is None
    assert len(res.citations) == 2
    assert res.used_graph is True


@pytest.mark.asyncio
async def test_query_blank_or_no_tenant_returns_empty() -> None:
    assert (await rt.graph_rag_query("", tenant_id="t1")).answer is None
    assert (await rt.graph_rag_query("q", tenant_id="")).answer is None
