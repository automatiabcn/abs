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

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
)

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
    # Char-based chunking (founder feedback 2026-06-06: cap ~400 chars).
    target_chars: int = Field(default=400, ge=80, le=4_000)
    overlap_chars: int = Field(default=80, ge=0, le=1_000)
    # Legacy token params still accepted; override char targets when provided.
    target_tokens: int | None = Field(default=None, ge=16, le=2048)
    overlap_tokens: int | None = Field(default=None, ge=0, le=512)


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
    # Founder feedback 2026-06-06: re-interpret the vector hits into an answer
    # ("chunk sonucunu verirsen doğru olmaz, yarım kalır") + metadata filtering.
    answer: bool = Field(
        default=False, description="LLM-synthesize an answer from the hits"
    )
    doc_ids: list[str] | None = Field(
        default=None, description="restrict the search to these document ids"
    )


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
    answer: str | None = None


def _active_project(request: Request, auth: AuthContext) -> str | None:
    """MT Phase 1 (B4) — resolve + authorize the X-Project-Id header. Returns
    the project slug when set + the caller may access it, else None."""
    from app.api.v1.project_context import resolve_active_project

    return resolve_active_project(
        request,
        tenant_slug=auth.tenant_id or "",
        subject=auth.subject or "",
        roles=auth.roles or [],
    )


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


def _synthesize_answer(
    query_text: str,
    hits: list["Hit"],
    tenant_id: str,
    *,
    project_slug: str | None = None,
    user_subject: str | None = None,
) -> str | None:
    """Re-interpret the retrieved chunks into a grounded answer (founder
    feedback: returning raw chunks "yarım kalır"). Best-effort: returns None if
    no provider is configured or the cascade fails — the caller still returns
    the hits. Runs the async cascade via asyncio.run (safe in the sync RAG
    route's threadpool, same constraint as the Cohere embedder)."""
    import asyncio

    from app.cascade.orchestrator import call_with_cascade
    from app.providers.cascade import get_active_providers

    active = get_active_providers()
    if not active or not hits:
        return None
    numbered = "\n\n".join(
        f"[{i + 1}] {h.text[:1200]}" for i, h in enumerate(hits)
    )
    prompt = (
        "Answer the question using ONLY the numbered sources below. Cite the "
        "sources you use inline as [1], [2]. If the sources don't contain the "
        "answer, say you don't have enough information. Reply in the same "
        "language as the question.\n\n"
        f"SOURCES:\n{numbered}\n\nQUESTION: {query_text}"
    )
    primary, *rest = active

    async def _run() -> str:
        resp = await call_with_cascade(
            prompt,
            primary=primary,
            fallbacks=tuple(rest),
            tenant_id=tenant_id or "_global",
            project_slug=project_slug,
            user_subject=user_subject,
            max_tokens=700,
            temperature=0.2,
        )
        return getattr(resp, "text", "") or ""

    try:
        return asyncio.run(_run()) or None
    except Exception as exc:  # noqa: BLE001 — answer is best-effort
        logger.info("rag answer synthesis failed (returning hits only): %s", exc)
        return None


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
    project_id: str | None = None,
) -> int:
    if not chunks:
        return 0
    embedder = _ensure_embedder()
    _ensure_qdrant_collection(collection, vector_size=embedder.dim)
    # Embedding is a network call (Cohere BYOK) — a rate-limit / auth / transient
    # provider error here must surface as a clean 503 the panel can render, not
    # an uncaught 500. (This path is shared by /ingest and /ingest-file.)
    try:
        vectors = embedder.embed([c.text for c in chunks])
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag_embed_failed: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"embedding_failed: {str(exc)[:160]}",
        ) from exc
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
                # MT Phase 1 (B4): per-project isolation, additive — only set
                # when an active project is selected; legacy chunks omit it.
                **({"project_id": project_id} if project_id else {}),
            },
        )
        for chunk, vec in zip(chunks, vectors)
    ]
    try:
        return qc.upsert_points(
            collection=collection, tenant_id=tenant_id, points=points
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag_upsert_failed: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"qdrant_upsert_failed: {str(exc)[:160]}",
        ) from exc


@router.post("/ingest", response_model=IngestResponse)
@observe(name="rag.ingest")
def ingest_text(
    body: IngestTextRequest,
    request: Request,
    rag: RAGAuth = Depends(rag_action_dep("ingest")),
) -> IngestResponse:
    auth = rag.auth
    collection = _tenant_collection(auth)
    project_id = _active_project(request, auth)
    started = time.perf_counter()
    # A binary mime (PDF/DOCX) sent through the JSON /ingest path means a stale
    # frontend POSTed file.text()-corrupted bytes — parsing fails. Surface a
    # clean 422 (use /ingest-file for binary) instead of an uncaught 500.
    try:
        doc = parse_document(
            body.text.encode("utf-8"),
            mime_type=body.mime_type,
            filename=body.filename,
        )
    except RuntimeError as exc:
        logger.warning("rag_ingest_parse_failed mime=%s err=%s", body.mime_type, exc)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{str(exc)[:140]} — binary files (PDF/DOCX) must be uploaded "
                "via /v1/rag/ingest-file, not the text /ingest path."
            ),
        ) from exc
    chunks = late_chunks(
        doc,
        target_chars=body.target_chars,
        overlap_chars=body.overlap_chars,
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
        project_id=project_id,
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


_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EXT_MIME = {
    ".pdf": "application/pdf",
    ".docx": _DOCX_MIME,
    ".xlsx": _XLSX_MIME,
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".json": "application/json",
}


@router.post("/ingest-file", response_model=IngestResponse)
@observe(name="rag.ingest_file")
def ingest_file(
    request: Request,
    file: UploadFile = File(...),
    rag: RAGAuth = Depends(rag_action_dep("ingest")),
) -> IngestResponse:
    """Ingest a real document (PDF / DOCX / txt / md) sent as raw multipart.

    Binary formats (PDF/DOCX) cannot go through `/ingest` — the browser would
    have to decode them to text first, which corrupts the bytes. Here the raw
    payload is parsed server-side (pypdf / python-docx) before chunking.

    MUST stay a SYNC `def` (like /ingest and /query): the embedding path calls
    `asyncio.run()` for the Cohere backend, which only works off the event loop
    (FastAPI runs sync routes in a threadpool). An `async def` here crashes with
    "asyncio.run() cannot be called from a running event loop" — and only with
    the real cohere backend, not the mock used in unit tests.
    """
    import os as _os

    auth = rag.auth
    collection = _tenant_collection(auth)
    # Sync read off the underlying SpooledTemporaryFile (no `await` in a sync route).
    raw = file.file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="empty_upload")

    # Resolve MIME from the extension first — browsers often send a generic
    # application/octet-stream for .docx, which the parser can't route.
    ext = _os.path.splitext(file.filename or "")[1].lower()
    mime = _EXT_MIME.get(ext) or (file.content_type or "application/octet-stream")

    started = time.perf_counter()
    try:
        doc = parse_document(raw, mime_type=mime, filename=file.filename)
    except RuntimeError as exc:
        # Parser errors (scanned PDF with no text layer, unsupported type) are
        # client-actionable — surface a clean 422 the panel can render.
        logger.warning("rag_ingest_file_parse_failed mime=%s err=%s", mime, exc)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    chunks = late_chunks(doc)
    if not chunks:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="no_chunkable_content"
        )

    project_id = _active_project(request, auth)
    inserted = _ingest_chunks(
        tenant_id=auth.tenant_id or "",
        collection=collection,
        chunks=chunks,
        project_id=project_id,
    )
    elapsed = (time.perf_counter() - started) * 1000.0
    tokens = estimate_token_count(doc.text)
    logger.info(
        "rag_ingest_file tenant=%s doc=%s mime=%s chunks=%d ms=%.1f",
        auth.tenant_id,
        doc.doc_id,
        mime,
        inserted,
        elapsed,
    )
    get_usage_logger().record(
        make_event(
            name="rag.ingest_file",
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
                "filename": file.filename or "",
                "mime": mime,
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
    request: Request,
    rag: RAGAuth = Depends(rag_action_dep("query")),
) -> QueryResponse:
    auth = rag.auth
    collection = _tenant_collection(auth)
    project_id = _active_project(request, auth)
    started = time.perf_counter()
    embedder = _ensure_embedder()
    _ensure_qdrant_collection(collection, vector_size=embedder.dim)
    vector = embedder.embed_one(body.query)
    must: list = []
    if body.doc_ids:
        # Metadata filter (founder feedback: "metadata kullanmazsan sonuçları
        # filtreleyemezsin") — restrict retrieval to the chosen documents.
        must.append(
            FieldCondition(
                key="doc_id", match=MatchAny(any=[d for d in body.doc_ids if d])
            )
        )
    if project_id:
        # MT Phase 1 (B4) — scope retrieval to the active project's chunks.
        must.append(
            FieldCondition(key="project_id", match=MatchValue(value=project_id))
        )
    extra_filter = Filter(must=must) if must else None
    try:
        raw_hits = qc.search(
            collection=collection,
            tenant_id=auth.tenant_id or "",
            query_vector=vector,
            limit=body.limit,
            score_threshold=body.score_threshold,
            extra_filter=extra_filter,
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
    answer = (
        _synthesize_answer(
            body.query,
            hits,
            auth.tenant_id or "",
            project_slug=project_id,
            user_subject=auth.subject,
        )
        if body.answer
        else None
    )
    return QueryResponse(
        query=body.query, hits=hits, elapsed_ms=elapsed, answer=answer
    )


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


@router.delete("/documents/{doc_id}")
@observe(name="rag.delete_document")
def delete_document(
    doc_id: str,
    rag: RAGAuth = Depends(rag_action_dep("ingest")),
) -> dict[str, Any]:
    """Delete a document (all its chunks) from the caller's tenant collection.

    Founder feedback 2026-06-06: "yüklenilen dosyaları sil özelliği de olmalı".
    Tenant-scoped via the Qdrant filter, so a caller can only delete their own
    documents. Idempotent: deleting an unknown doc_id returns deleted=0.
    """
    auth = rag.auth
    collection = _tenant_collection(auth)
    if not (doc_id or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "doc_id_required")
    try:
        removed = qc.delete_document(
            collection=collection, tenant_id=auth.tenant_id or "", doc_id=doc_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag_delete_document_failed: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"qdrant_unavailable: {exc}",
        ) from exc
    logger.info(
        "rag_delete_document tenant=%s doc_id=%s removed=%d",
        auth.tenant_id,
        doc_id,
        removed,
    )
    return {"doc_id": doc_id, "deleted": removed}
