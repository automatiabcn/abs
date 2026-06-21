# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""GraphRAG API — build a knowledge graph over the RAG corpus + hybrid query.

`POST /v1/graph-rag/build`  — (re)process the tenant's already-ingested chunks
                              into Neo4j entities/relations (LLM extraction).
`POST /v1/graph-rag/query`  — vector top-k + 1-hop graph expansion + grounded
                              synthesis with chunk-level citations.

Both are tenant-scoped via the existing Cerbos RAG dependency. Build is an
`ingest` action; query is a `query` action. Routes are always registered; the
`graphrag_enabled` setting only gates the best-effort ingest auto-hook.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.middleware.cerbos_rag_filter import RAGAuth, rag_action_dep
from app.observability.langfuse_client import observe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/graph-rag", tags=["graph-rag"])


def _require_graphrag_enabled() -> None:
    """GraphRAG is opt-in. When off, the surface returns 404 so a customer who
    doesn't use it sees no half-wired endpoints."""
    if not settings.graphrag_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="graphrag_disabled"
        )


class BuildRequest(BaseModel):
    doc_id: str | None = Field(
        default=None, description="restrict the build to a single document"
    )
    rebuild: bool = Field(
        default=False,
        description="purge the targeted doc(s) from the graph before re-extracting",
    )


class BuildResponse(BaseModel):
    docs: int
    chunks_processed: int
    entities: int
    relations: int
    skipped: int


class GraphRagQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4_000)
    limit: int = Field(default=5, ge=1, le=50)
    synthesize: bool = Field(
        default=True, description="run LLM synthesis over chunks + subgraph"
    )
    depth: int = Field(
        default=1, ge=1, le=3,
        description="graph traversal depth (1=immediate edges, up to 3 hops)",
    )


@router.post("/build", response_model=BuildResponse)
@observe(name="graph_rag.build")
async def build(
    body: BuildRequest,
    rag: RAGAuth = Depends(rag_action_dep("ingest")),
) -> BuildResponse:
    _require_graphrag_enabled()
    from app.graph_rag.extract import extract_graph
    from app.graph_rag.store import purge_doc_graph, store_chunk_graph
    from app.providers.cascade import get_active_providers
    from app.rag import qdrant_client as qc

    tenant = rag.tenant_id
    if not get_active_providers():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "no_providers_configured",
                "hint": "Configure an LLM provider key to extract the graph.",
            },
        )

    collection = settings.qdrant_default_collection
    try:
        chunks = await asyncio.to_thread(
            qc.iter_chunks,
            collection=collection,
            tenant_id=tenant,
            doc_id=body.doc_id,
            max_points=settings.graphrag_build_max_chunks,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("graphrag_build_scroll_failed: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"qdrant_unavailable: {exc}",
        ) from exc

    if not chunks:
        return BuildResponse(
            docs=0, chunks_processed=0, entities=0, relations=0, skipped=0
        )

    from app.integrations.neo4j_client import Neo4jClient

    client = Neo4jClient()
    if not await client.health():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="neo4j_unavailable"
        )

    if body.rebuild:
        for doc in {c["doc_id"] for c in chunks if c["doc_id"]}:
            try:
                await purge_doc_graph(client, tenant_id=tenant, doc_id=doc)
            except Exception as exc:  # noqa: BLE001
                logger.info("graphrag purge failed for %s: %s", doc, exc)

    docs: set[str] = set()
    total_entities = total_relations = processed = skipped = 0
    for chunk in chunks:
        text = chunk.get("text") or ""
        if not text.strip():
            skipped += 1
            continue
        try:
            result = await extract_graph(text, tenant_id=tenant)
            counts = await store_chunk_graph(
                client,
                tenant_id=tenant,
                doc_id=chunk["doc_id"],
                chunk_id=chunk["chunk_id"],
                seq=chunk["seq"],
                result=result,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort per chunk
            logger.info("graphrag chunk %s failed: %s", chunk.get("chunk_id"), exc)
            skipped += 1
            continue
        total_entities += counts["entities"]
        total_relations += counts["relations"]
        processed += 1
        if chunk["doc_id"]:
            docs.add(chunk["doc_id"])

    logger.info(
        "graphrag_build tenant=%s docs=%d chunks=%d entities=%d relations=%d skipped=%d",
        tenant,
        len(docs),
        processed,
        total_entities,
        total_relations,
        skipped,
    )
    return BuildResponse(
        docs=len(docs),
        chunks_processed=processed,
        entities=total_entities,
        relations=total_relations,
        skipped=skipped,
    )


@router.post("/query")
@observe(name="graph_rag.query")
async def query(
    body: GraphRagQueryRequest,
    rag: RAGAuth = Depends(rag_action_dep("query")),
) -> dict[str, Any]:
    _require_graphrag_enabled()
    from app.graph_rag.retrieve import graph_rag_query

    try:
        result = await graph_rag_query(
            body.query,
            tenant_id=rag.tenant_id,
            top_k=body.limit,
            synthesize=body.synthesize,
            depth=body.depth,
        )
    except ImportError as exc:  # embedder backend missing
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"embedder_unavailable: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001 — Qdrant outage etc.
        logger.warning("graphrag_query_failed: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"graph_rag_query_failed: {exc}",
        ) from exc
    return result.as_dict()
