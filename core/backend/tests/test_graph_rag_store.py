"""GraphRAG — Neo4j store unit tests (fake async client; no live Neo4j)."""

from __future__ import annotations

import pytest

from app.graph_rag.extract import (
    ExtractedEntity,
    ExtractedRelation,
    ExtractionResult,
)
from app.graph_rag.store import purge_doc_graph, store_chunk_graph


class _FakeNeo4j:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        params = params or {}
        self.calls.append((cypher, params))
        if "RETURN count(e)" in cypher:
            return [{"entities": len(params.get("entities", []))}]
        if "RETURN count(r)" in cypher:
            return [{"relations": len(params.get("relations", []))}]
        return []


def _result() -> ExtractionResult:
    return ExtractionResult(
        entities=[
            ExtractedEntity(id="person:ahmet", name="Ahmet", type="Person"),
            ExtractedEntity(id="organization:abc", name="ABC", type="Organization"),
        ],
        relations=[
            ExtractedRelation(
                source_id="person:ahmet", target_id="organization:abc", type="WORKS_AT"
            )
        ],
    )


@pytest.mark.asyncio
async def test_store_chunk_graph_writes_entities_and_relations() -> None:
    client = _FakeNeo4j()
    counts = await store_chunk_graph(
        client,
        tenant_id="t1",
        doc_id="doc1",
        chunk_id="c1",
        seq=0,
        result=_result(),
    )
    assert counts == {"entities": 2, "relations": 1}
    # Every query must carry the tenant_id param (isolation).
    assert all(params.get("tenant_id") == "t1" for _, params in client.calls)
    # Entities query ran before relations query.
    kinds = [c for c, _ in client.calls]
    assert any("RETURN count(e)" in k for k in kinds)
    assert any("RETURN count(r)" in k for k in kinds)


@pytest.mark.asyncio
async def test_store_chunk_graph_empty_result_still_merges_chunk() -> None:
    client = _FakeNeo4j()
    counts = await store_chunk_graph(
        client,
        tenant_id="t1",
        doc_id="doc1",
        chunk_id="c-empty",
        seq=3,
        result=ExtractionResult(),
    )
    assert counts == {"entities": 0, "relations": 0}
    assert len(client.calls) == 1
    cypher, params = client.calls[0]
    assert "MERGE (c:GraphChunk" in cypher
    assert params["chunk_id"] == "c-empty"
    assert params["tenant_id"] == "t1"


@pytest.mark.asyncio
async def test_store_chunk_graph_skips_relation_query_when_no_relations() -> None:
    client = _FakeNeo4j()
    res = ExtractionResult(
        entities=[ExtractedEntity(id="concept:x", name="X", type="Concept")],
        relations=[],
    )
    counts = await store_chunk_graph(
        client, tenant_id="t1", doc_id="d", chunk_id="c", seq=0, result=res
    )
    assert counts == {"entities": 1, "relations": 0}
    assert not any("RETURN count(r)" in c for c, _ in client.calls)


@pytest.mark.asyncio
async def test_store_chunk_graph_requires_tenant_and_chunk() -> None:
    client = _FakeNeo4j()
    with pytest.raises(ValueError):
        await store_chunk_graph(
            client, tenant_id="", doc_id="d", chunk_id="c", seq=0, result=_result()
        )
    with pytest.raises(ValueError):
        await store_chunk_graph(
            client, tenant_id="t1", doc_id="d", chunk_id="", seq=0, result=_result()
        )


@pytest.mark.asyncio
async def test_purge_doc_graph_runs_three_scoped_queries() -> None:
    client = _FakeNeo4j()
    await purge_doc_graph(client, tenant_id="t1", doc_id="doc1")
    assert len(client.calls) == 3
    assert all(params.get("tenant_id") == "t1" for _, params in client.calls)
    joined = " ".join(c for c, _ in client.calls)
    assert "DELETE r" in joined  # relations
    assert "DETACH DELETE c" in joined  # chunks
    assert "DETACH DELETE e" in joined  # orphan entities
