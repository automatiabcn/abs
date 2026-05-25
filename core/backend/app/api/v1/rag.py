# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-011 — RAG ingest + query endpoints (v10 pipeline).

`/v1/rag/ingest` — accept JSON body or multipart upload, parse → late-chunk →
embed → upsert into Qdrant under the caller's tenant.
`/v1/rag/query` — embed the query, search the tenant's collection, return
top-K hits.

JWT-authenticated via `get_auth_context` (T-005) and tenant-scoped via the
Qdrant wrapper (T-009). Cerbos resource-level policy is added in T-012.
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from qdrant_client.models import PointStruct

from app.api.v1.deps import AuthContext, get_auth_context
from app.config import settings
from app.middleware.cerbos_rag_filter import RAGAuth, rag_action_dep
from app.observability.langfuse_client import observe
from app.observability.usage_logger import get_usage_logger, make_event
from app.rag import qdrant_client as qc
from app.rag.embedding_bge import get_embedder
from app.rag.pipeline_v10 import (
    Chunk,
    estimate_token_count,
    late_chunks,
    parse_document,
)
from app.rag.reranker import get_reranker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/rag", tags=["rag"])


class IngestTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2_000_000)
    filename: str | None = None
    mime_type: str = "text/plain"
    contextual_prefix: str | None = Field(default=None, max_length=4_000)
    target_tokens: int = Field(default=512, ge=64, le=2048)
    overlap_tokens: int = Field(default=64, ge=0, le=512)


class IngestResponse(BaseModel):
    doc_id: str
    chunks: int
    tokens_estimated: int
    collection: str
    elapsed_ms: float


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4_000)
    limit: int = Field(default=5, ge=1, le=50)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank: bool = Field(default=False, description="apply T-013 cross-encoder rerank")
    rerank_top_k: int = Field(default=3, ge=1, le=50)


class Hit(BaseModel):
    chunk_id: str
    score: float
    text: str
    doc_id: str
    seq: int
    metadata: dict[str, Any]


class QueryResponse(BaseModel):
    query: str
    hits: list[Hit]
    elapsed_ms: float


def _tenant_collection(auth: AuthContext) -> str:
    if not auth.tenant_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="missing_tenant_claim"
        )
    return settings.qdrant_default_collection


def _ensure_embedder():
    """BUG-27 — surface embedder import/init failures as 503 instead of 500.

    The customer image ships with the deterministic `mock` backend by
    default; switching to `sentence_transformers` requires the optional
    library + a 2 GB BGE-M3 download. If the operator flips
    `ABS_EMBEDDING_BACKEND=sentence_transformers` without installing the
    package the server now returns a clean 503 the panel can render —
    historically this was a 500 with a Python ImportError leaking out.
    """
    try:
        return get_embedder()
    except ImportError as exc:
        logger.warning("embedder_unavailable_import: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"embedder_unavailable: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedder_unavailable_init: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"embedder_unavailable: {exc}",
        ) from exc


def _ensure_qdrant_collection(collection: str, vector_size: int) -> None:
    """Like _ensure_embedder above but for the Qdrant TCP connection. The
    customer compose ships qdrant alongside the backend, so this normally
    succeeds; if the service is mid-restart we surface 503 with a hint."""
    try:
        qc.ensure_collection(collection, vector_size=vector_size)
    except Exception as exc:  # noqa: BLE001
        logger.warning("qdrant_unavailable: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"qdrant_unavailable: {exc}",
        ) from exc


def _ingest_chunks(
    *,
    tenant_id: str,
    collection: str,
    chunks: list[Chunk],
) -> int:
    if not chunks:
        return 0
    embedder = _ensure_embedder()
    _ensure_qdrant_collection(collection, vector_size=embedder.dim)
    vectors = embedder.embed([c.text for c in chunks])
    now = int(time.time())
    points = [
        PointStruct(
            id=chunk.chunk_id,
            vector=vec,
            payload={
                "tenant_id": tenant_id,
                "doc_id": chunk.doc_id,
                "chunk_id": chunk.chunk_id,
                "seq": chunk.seq,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "text": chunk.raw_text,
                "created_at": now,
                **chunk.metadata,
            },
        )
        for chunk, vec in zip(chunks, vectors)
    ]
    return qc.upsert_points(
        collection=collection, tenant_id=tenant_id, points=points
    )


@router.post("/ingest", response_model=IngestResponse)
@observe(name="rag.ingest")
def ingest_text(
    body: IngestTextRequest,
    rag: RAGAuth = Depends(rag_action_dep("ingest")),
) -> IngestResponse:
    auth = rag.auth
    collection = _tenant_collection(auth)
    started = time.perf_counter()
    doc = parse_document(
        body.text.encode("utf-8"), mime_type=body.mime_type, filename=body.filename
    )
    chunks = late_chunks(
        doc,
        target_tokens=body.target_tokens,
        overlap_tokens=body.overlap_tokens,
        contextual_prefix=body.contextual_prefix,
    )
    if not chunks:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="no_chunkable_content"
        )

    inserted = _ingest_chunks(
        tenant_id=auth.tenant_id or "",
        collection=collection,
        chunks=chunks,
    )
    elapsed = (time.perf_counter() - started) * 1000.0
    tokens = estimate_token_count(doc.text)
    logger.info(
        "rag_ingest tenant=%s doc=%s chunks=%d ms=%.1f",
        auth.tenant_id,
        doc.doc_id,
        inserted,
        elapsed,
    )
    get_usage_logger().record(
        make_event(
            name="rag.ingest",
            tenant_id=auth.tenant_id,
            user_subject=auth.subject,
            request_type="ingest",
            status="ok",
            latency_ms=elapsed,
            input_tokens=tokens,
            output_tokens=inserted,
            model_version=f"bge-m3-{settings.embedding_backend}",
            metadata={
                "doc_id": doc.doc_id,
                "collection": collection,
                "chunks": inserted,
                "filename": body.filename or "",
            },
        )
    )
    return IngestResponse(
        doc_id=doc.doc_id,
        chunks=inserted,
        tokens_estimated=tokens,
        collection=collection,
        elapsed_ms=elapsed,
    )


@router.post("/query", response_model=QueryResponse)
@observe(name="rag.query")
def query(
    body: QueryRequest,
    rag: RAGAuth = Depends(rag_action_dep("query")),
) -> QueryResponse:
    auth = rag.auth
    collection = _tenant_collection(auth)
    started = time.perf_counter()
    embedder = _ensure_embedder()
    _ensure_qdrant_collection(collection, vector_size=embedder.dim)
    vector = embedder.embed_one(body.query)
    try:
        raw_hits = qc.search(
            collection=collection,
            tenant_id=auth.tenant_id or "",
            query_vector=vector,
            limit=body.limit,
            score_threshold=body.score_threshold,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("qdrant_search_failed: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"qdrant_search_failed: {exc}",
        ) from exc

    if body.rerank and raw_hits:
        reranker = get_reranker()
        results = reranker.rerank(
            body.query,
            [str(h["payload"].get("text", "")) for h in raw_hits],
            top_k=min(body.rerank_top_k, len(raw_hits)),
        )
        raw_hits = [
            {
                **raw_hits[r.index],
                "score": float(r.score),
            }
            for r in results
        ]

    elapsed = (time.perf_counter() - started) * 1000.0
    hits = [
        Hit(
            chunk_id=str(h["payload"].get("chunk_id") or h["id"]),
            score=h["score"],
            text=str(h["payload"].get("text", "")),
            doc_id=str(h["payload"].get("doc_id", "")),
            seq=int(h["payload"].get("seq", 0)),
            metadata={
                k: v
                for k, v in h["payload"].items()
                if k not in {"text", "tenant_id"}
            },
        )
        for h in raw_hits
    ]
    logger.info(
        "rag_query tenant=%s q_len=%d hits=%d ms=%.1f",
        auth.tenant_id,
        len(body.query),
        len(hits),
        elapsed,
    )
    get_usage_logger().record(
        make_event(
            name="rag.query",
            tenant_id=auth.tenant_id,
            user_subject=auth.subject,
            request_type="query",
            status="ok",
            latency_ms=elapsed,
            input_tokens=estimate_token_count(body.query),
            output_tokens=len(hits),
            model_version=f"bge-m3-{settings.embedding_backend}",
            metadata={
                "limit": body.limit,
                "rerank": body.rerank,
                "hits": len(hits),
            },
        )
    )
    return QueryResponse(query=body.query, hits=hits, elapsed_ms=elapsed)


@router.get("/documents")
@observe(name="rag.documents")
def list_documents(
    rag: RAGAuth = Depends(rag_action_dep("query")),
) -> dict[str, Any]:
    """Document inventory for the caller's tenant — groups stored chunks by
    ``doc_id``. Powers the admin RAG page so a reload shows the real indexed
    corpus (not just this session's uploads). Tolerant of a missing
    collection / Qdrant outage → empty inventory rather than 5xx.
    """
    auth = rag.auth
    collection = _tenant_collection(auth)
    try:
        raw = qc.list_documents(
            collection=collection, tenant_id=auth.tenant_id or ""
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag_documents_unavailable: %s", exc)
        raw = []
    documents = [
        {
            "id": d["doc_id"],
            "filename": d["filename"] or d["doc_id"],
            "chunks": int(d["chunks"]),
            "size_bytes": int(d["bytes"]),
            "ingested_at": (
                _dt.datetime.fromtimestamp(
                    d["created_at"], _dt.timezone.utc
                ).isoformat()
                if d.get("created_at")
                else None
            ),
        }
        for d in raw
    ]
    return {
        "collection": collection,
        "documents": documents,
        "doc_count": len(documents),
        "chunk_count": sum(d["chunks"] for d in documents),
        "total_bytes": sum(d["size_bytes"] for d in documents),
    }
