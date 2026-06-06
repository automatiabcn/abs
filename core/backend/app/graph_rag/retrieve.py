# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""GraphRAG hybrid retrieval.

vector top-k (Qdrant, tenant-scoped) → collect chunk ids → expand 1-hop around
the entities mentioned in those chunks (Neo4j, tenant-scoped) → synthesize an
answer grounded in (chunks + subgraph) with chunk-level citations.

Degrades gracefully and independently at each stage:
  * no vectors        → empty result (answer None)
  * Neo4j unavailable → chunks-only answer (used_graph False)
  * no LLM provider   → retrieval returned without a synthesized answer
The embedder + Qdrant search run on a worker thread (`asyncio.to_thread`)
because the Cohere embedder calls `asyncio.run()` internally and must not see a
running event loop.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GraphCitation:
    chunk_id: str
    source: str
    excerpt: str
    score: float | None
    doc_id: str | None = None


@dataclass(slots=True)
class GraphRagResult:
    answer: str | None
    citations: list[GraphCitation] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    used_graph: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [
                {
                    "chunk_id": c.chunk_id,
                    "source": c.source,
                    "excerpt": c.excerpt,
                    "score": c.score,
                    "doc_id": c.doc_id,
                }
                for c in self.citations
            ],
            "entities": self.entities,
            "relations": self.relations,
            "used_graph": self.used_graph,
        }


_SUBGRAPH_CYPHER = """
MATCH (e:GraphEntity {tenant_id: $tenant_id})-[:MENTIONED_IN]->(c:GraphChunk {tenant_id: $tenant_id})
WHERE c.id IN $chunk_ids
WITH collect(DISTINCT e) AS seeds
UNWIND seeds AS e
OPTIONAL MATCH (e)-[r:REL {tenant_id: $tenant_id}]->(e2:GraphEntity {tenant_id: $tenant_id})
RETURN e.id AS src_id, e.name AS src_name, e.type AS src_type,
       r.type AS rel_type,
       e2.id AS dst_id, e2.name AS dst_name, e2.type AS dst_type
"""


def _vector_search(query: str, tenant_id: str, top_k: int) -> list[dict[str, Any]]:
    """Sync Qdrant search (runs on a worker thread). Returns hit dicts."""
    from app.config import settings
    from app.rag import qdrant_client as qc
    from app.rag.embedding_bge import get_embedder

    embedder = get_embedder()
    vector = embedder.embed_one(query)
    hits = qc.search(
        collection=settings.qdrant_default_collection,
        tenant_id=tenant_id,
        query_vector=vector,
        limit=top_k,
    )
    return hits or []


def _hits_to_citations(hits: list[dict[str, Any]]) -> list[GraphCitation]:
    cites: list[GraphCitation] = []
    for h in hits:
        payload = h.get("payload") or {}
        source = str(payload.get("filename") or payload.get("doc_id") or "document")
        excerpt = str(payload.get("text") or "")[:280]
        score = h.get("score")
        cites.append(
            GraphCitation(
                chunk_id=str(payload.get("chunk_id") or h.get("id") or ""),
                source=source,
                excerpt=excerpt,
                score=float(score) if score is not None else None,
                doc_id=payload.get("doc_id"),
            )
        )
    return cites


async def _fetch_subgraph(
    client: Any, tenant_id: str, chunk_ids: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """1-hop subgraph around entities mentioned in `chunk_ids`. Best-effort."""
    if not chunk_ids:
        return [], []
    try:
        rows = await client.query(
            _SUBGRAPH_CYPHER, {"tenant_id": tenant_id, "chunk_ids": chunk_ids}
        )
    except Exception as exc:  # Neo4j down / query error → chunks-only
        logger.info("graphrag subgraph query failed (degrading): %s", exc)
        return [], []

    entities: dict[str, dict[str, Any]] = {}
    relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows or []:
        src_id = row.get("src_id")
        if src_id and src_id not in entities:
            entities[src_id] = {
                "id": src_id,
                "name": row.get("src_name"),
                "type": row.get("src_type"),
            }
        dst_id = row.get("dst_id")
        if dst_id and dst_id not in entities:
            entities[dst_id] = {
                "id": dst_id,
                "name": row.get("dst_name"),
                "type": row.get("dst_type"),
            }
        rel_type = row.get("rel_type")
        if src_id and dst_id and rel_type:
            key = (src_id, dst_id, rel_type)
            if key not in relations:
                relations[key] = {
                    "source_id": src_id,
                    "target_id": dst_id,
                    "type": rel_type,
                }
    return list(entities.values()), list(relations.values())


def _build_synthesis_prompt(
    query: str,
    citations: list[GraphCitation],
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> str:
    chunk_lines = "\n\n".join(
        f"[{i + 1}] ({c.source})\n{c.excerpt}" for i, c in enumerate(citations)
    )
    name_by_id = {e["id"]: (e.get("name") or e["id"]) for e in entities}
    triple_lines = "\n".join(
        f"- {name_by_id.get(r['source_id'], r['source_id'])} "
        f"--{r['type']}--> {name_by_id.get(r['target_id'], r['target_id'])}"
        for r in relations
    )
    graph_block = (
        f"\n\nKNOWLEDGE GRAPH (entities + relations connected to the sources):\n{triple_lines}"
        if triple_lines
        else ""
    )
    return (
        "Answer the question using ONLY the sources and knowledge graph below. "
        "Cite sources inline as [1], [2] matching the numbered passages. If the "
        "answer is not contained in the material, say you don't have enough "
        "information. Answer in the same language as the question.\n\n"
        f"SOURCES:\n{chunk_lines}{graph_block}\n\n"
        f"QUESTION: {query}"
    )


async def _synthesize(prompt: str, tenant_id: str) -> str | None:
    """LLM synthesis via cascade. Returns None if no provider / all failed."""
    try:
        from app.graph_rag.extract import _run_llm

        return await _run_llm(prompt, tenant_id=tenant_id, use_cache=True)
    except Exception as exc:
        logger.info("graphrag synthesis unavailable (degrading): %s", exc)
        return None


async def graph_rag_query(
    query: str,
    *,
    tenant_id: str,
    top_k: int = 5,
    synthesize: bool = True,
    neo4j_client: Any = None,
) -> GraphRagResult:
    """Hybrid GraphRAG query. `tenant_id` scopes both Qdrant and Neo4j."""
    q = (query or "").strip()
    tenant = (tenant_id or "").strip()
    if not q or not tenant:
        return GraphRagResult(answer=None)

    hits = await asyncio.to_thread(_vector_search, q, tenant, top_k)
    citations = _hits_to_citations(hits)
    if not citations:
        return GraphRagResult(answer=None)

    if neo4j_client is None:
        from app.integrations.neo4j_client import Neo4jClient

        neo4j_client = Neo4jClient()
    chunk_ids = [c.chunk_id for c in citations if c.chunk_id]
    entities, relations = await _fetch_subgraph(neo4j_client, tenant, chunk_ids)

    answer: str | None = None
    if synthesize:
        prompt = _build_synthesis_prompt(q, citations, entities, relations)
        answer = await _synthesize(prompt, tenant)

    return GraphRagResult(
        answer=answer,
        citations=citations,
        entities=entities,
        relations=relations,
        used_graph=bool(entities),
    )
