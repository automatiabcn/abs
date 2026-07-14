# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""RAG ingest + query endpoints (v10 pipeline).

`/v1/rag/ingest` — accept JSON body or multipart upload, parse → late-chunk →
embed → upsert into Qdrant under the caller's tenant.
`/v1/rag/query` — embed the query, search the tenant's collection, return
top-K hits.

JWT-authenticated via `get_auth_context` and tenant-scoped via the
Qdrant wrapper. Cerbos adds the resource-level policy on top.
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

from app.api.v1.deps import AuthContext
from app.config import settings
from app.middleware.cerbos_rag_filter import RAGAuth, rag_action_dep
from app.observability.langfuse_client import observe
from app.observability.usage_logger import get_usage_logger, make_event
from app.rag import qdrant_client as qc
from app.rag.embedding_bge import get_embedder, model_id_of
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
    # Char-based chunking, capped at ~400 chars.
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
    rerank: bool = Field(default=False, description="apply cross-encoder rerank")
    rerank_top_k: int = Field(default=3, ge=1, le=50)
    # Re-interpret the vector hits into a complete answer (returning raw chunks
    # leaves the response truncated) + metadata filtering.
    answer: bool = Field(
        default=False, description="LLM-synthesize an answer from the hits"
    )
    doc_ids: list[str] | None = Field(
        default=None, description="restrict the search to these document ids"
    )
    kinds: list[str] | None = Field(
        default=None,
        description=(
            "filter by chunk kind for the unified index: ['image'] = images "
            "only, ['text'] = exclude images (legacy text chunks have no kind), "
            "None/both = everything"
        ),
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
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="missing_tenant_claim")
    return settings.qdrant_default_collection


def _ensure_embedder():
    """surface embedder import/init failures as 503 instead of 500.

    The customer image ships with the deterministic `mock` backend by
    default; switching to `sentence_transformers` requires the optional
    library + a 2 GB BGE-M3 download. If the operator flips
    `ABS_EMBEDDING_BACKEND=sentence_transformers` without installing the
    package the server now returns a clean 503 the panel can render —
    historically this was a 500 with a Python ImportError leaking out.
    """
    try:
        embedder = get_embedder()
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

    # An embedder that does not understand meaning cannot search, and this is the
    # endpoint the panel's search box and the /rag command call. The guard existed
    # in chat's citation path and nowhere else, so the *main* surface went on
    # answering from sha256 vectors — confidently, with citations, from unrelated
    # documents. Refusing here is the difference between a customer seeing an
    # error and a customer being misled.
    if not embedder.semantic:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "search_unavailable: no embedding model is configured, so documents "
                "cannot be searched. Set ABS_EMBEDDING_BACKEND (ollama / "
                "sentence_transformers / cohere)."
            ),
        )
    return embedder


def _synthesize_answer(
    query_text: str,
    hits: list["Hit"],
    tenant_id: str,
    *,
    project_slug: str | None = None,
    user_subject: str | None = None,
) -> str | None:
    """Re-interpret the retrieved chunks into a grounded answer (returning raw
    chunks leaves the response truncated). Best-effort: returns None if
    no provider is configured or the cascade fails — the caller still returns
    the hits. Runs the async cascade via asyncio.run (safe in the sync RAG
    route's threadpool, same constraint as the Cohere embedder)."""
    import asyncio

    from app.cascade.orchestrator import call_with_cascade
    from app.providers.cascade import get_active_providers

    active = get_active_providers()
    if not active or not hits:
        return None
    numbered = "\n\n".join(f"[{i + 1}] {h.text[:1200]}" for i, h in enumerate(hits))
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
                # Which model made this vector. Vectors are only comparable to
                # others from the same model, so a corpus embedded before a
                # backend change has to be recognisable as stale — otherwise it
                # sits in the collection being counted and never found.
                "embed_model": model_id_of(embedder),
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="no_chunkable_content")

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


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="no_chunkable_content")

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


_IMAGE_EXT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MiB


@router.post("/ingest-image", response_model=IngestResponse)
@observe(name="rag.ingest_image")
def ingest_image(
    request: Request,
    file: UploadFile = File(...),
    rag: RAGAuth = Depends(rag_action_dep("ingest")),
) -> IngestResponse:
    """Ingest an IMAGE into the same RAG index as text.

    Gemini has no native image-embedding endpoint, so the image is vision-
    described by Gemini and that description is run through the normal text
    pipeline (embed → Qdrant) tagged ``kind="image"``. The image then becomes
    retrievable by the EXISTING text /query — one unified index, no separate
    vector space — and results carry the image metadata so the panel can badge
    or filter them (see QueryRequest.kinds).

    SYNC `def` for the same reason as /ingest-file (the embedder calls
    asyncio.run for the Cohere backend, which needs to be off the event loop);
    the Gemini describe call is driven with asyncio.run from this threadpool.
    """
    import asyncio
    import base64
    import os as _os

    from app.providers import gemini_extras
    from app.providers.schemas import ProviderError

    auth = rag.auth
    collection = _tenant_collection(auth)
    raw = file.file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="empty_upload")
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="image_too_large"
        )
    ext = _os.path.splitext(file.filename or "")[1].lower()
    ctype = (file.content_type or "").lower()
    mime = _IMAGE_EXT_MIME.get(ext) or (ctype if ctype.startswith("image/") else None)
    if not mime:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="unsupported_image_type (png/jpg/webp/gif)",
        )

    started = time.perf_counter()
    b64 = base64.b64encode(raw).decode("ascii")
    try:
        resp = asyncio.run(gemini_extras.describe_image(b64, mime))
    except ProviderError as exc:
        # No Gemini key / vision call failed — describe is the only embed path
        # for images, so surface a clean 503 the panel can render.
        logger.warning("rag_ingest_image_describe_failed: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"image_describe_unavailable: {str(exc)[:160]}",
        ) from exc
    desc = (resp.text or "").strip()
    if not desc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="image_not_describable"
        )

    # Reuse the text pipeline so the image-description gets the same chunking,
    # deterministic doc/chunk ids and embedding as any other document.
    doc = parse_document(
        desc.encode("utf-8"), mime_type="text/plain", filename=file.filename or "image"
    )
    chunks = late_chunks(doc)
    if not chunks:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="image_not_describable"
        )
    for c in chunks:
        c.metadata["kind"] = "image"
        c.metadata["source_filename"] = file.filename or ""
        c.metadata["image_mime"] = mime

    project_id = _active_project(request, auth)
    inserted = _ingest_chunks(
        tenant_id=auth.tenant_id or "",
        collection=collection,
        chunks=chunks,
        project_id=project_id,
    )
    elapsed = (time.perf_counter() - started) * 1000.0
    tokens = estimate_token_count(desc)
    logger.info(
        "rag_ingest_image tenant=%s doc=%s mime=%s chunks=%d ms=%.1f",
        auth.tenant_id,
        doc.doc_id,
        mime,
        inserted,
        elapsed,
    )
    get_usage_logger().record(
        make_event(
            name="rag.ingest_image",
            tenant_id=auth.tenant_id,
            user_subject=auth.subject,
            request_type="ingest",
            status="ok",
            latency_ms=elapsed,
            input_tokens=tokens,
            output_tokens=inserted,
            model_version=f"gemini-vision+{settings.embedding_backend}",
            metadata={
                "doc_id": doc.doc_id,
                "collection": collection,
                "chunks": inserted,
                "filename": file.filename or "",
                "kind": "image",
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


def _rag_extra_filter(
    *,
    project_id: str | None,
    kinds: list[str] | None,
    doc_ids: list[str] | None = None,
) -> Filter | None:
    """Shared metadata filter for /query and /query-by-image.

    Scopes retrieval to the chosen docs + active project, and applies the
    unified-index modality filter (images/text live in one collection; legacy
    text has no `kind`, so "text only" = must_not kind=image).
    """
    must: list = []
    must_not: list = []
    if doc_ids:
        must.append(
            FieldCondition(key="doc_id", match=MatchAny(any=[d for d in doc_ids if d]))
        )
    if project_id:
        must.append(
            FieldCondition(key="project_id", match=MatchValue(value=project_id))
        )
    if kinds:
        want = {k.strip().lower() for k in kinds if k}
        if want == {"image"}:
            must.append(FieldCondition(key="kind", match=MatchValue(value="image")))
        elif want and "image" not in want:
            must_not.append(FieldCondition(key="kind", match=MatchValue(value="image")))
    if not must and not must_not:
        return None
    return Filter(must=must or None, must_not=must_not or None)


def _raw_to_hits(raw_hits: list) -> list["Hit"]:
    """Map Qdrant payloads to Hit, surfacing all metadata except text/tenant_id."""
    return [
        Hit(
            chunk_id=str(h["payload"].get("chunk_id") or h["id"]),
            score=h["score"],
            text=str(h["payload"].get("text", "")),
            doc_id=str(h["payload"].get("doc_id", "")),
            seq=int(h["payload"].get("seq", 0)),
            metadata={
                k: v for k, v in h["payload"].items() if k not in {"text", "tenant_id"}
            },
        )
        for h in raw_hits
    ]


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
    extra_filter = _rag_extra_filter(
        project_id=project_id, kinds=body.kinds, doc_ids=body.doc_ids
    )
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
    hits = _raw_to_hits(raw_hits)
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
    return QueryResponse(query=body.query, hits=hits, elapsed_ms=elapsed, answer=answer)


class ImageQueryResponse(BaseModel):
    description: str  # what Gemini saw — the text actually searched
    hits: list[Hit]
    elapsed_ms: float


@router.post("/query-by-image", response_model=ImageQueryResponse)
@observe(name="rag.query_by_image")
def query_by_image(
    request: Request,
    file: UploadFile = File(...),
    limit: int = 5,
    kinds: str | None = None,
    rag: RAGAuth = Depends(rag_action_dep("query")),
) -> ImageQueryResponse:
    """Search the knowledge base USING an image as the query.

    The image is vision-described by Gemini, and that description is embedded
    and searched against the unified index — so an uploaded photo/screenshot
    finds related docs AND other images. ``kinds`` is an optional comma list
    ('image' / 'text') to scope the modality, same as /query. SYNC def for the
    same asyncio.run reason as the other image/embedding routes.
    """
    import asyncio
    import base64
    import os as _os

    from app.providers import gemini_extras
    from app.providers.schemas import ProviderError

    auth = rag.auth
    collection = _tenant_collection(auth)
    project_id = _active_project(request, auth)
    raw = file.file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="empty_upload")
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="image_too_large"
        )
    ext = _os.path.splitext(file.filename or "")[1].lower()
    ctype = (file.content_type or "").lower()
    mime = _IMAGE_EXT_MIME.get(ext) or (ctype if ctype.startswith("image/") else None)
    if not mime:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="unsupported_image_type (png/jpg/webp/gif)",
        )

    started = time.perf_counter()
    b64 = base64.b64encode(raw).decode("ascii")
    try:
        resp = asyncio.run(gemini_extras.describe_image(b64, mime))
    except ProviderError as exc:
        logger.warning("rag_query_by_image_describe_failed: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"image_describe_unavailable: {str(exc)[:160]}",
        ) from exc
    description = (resp.text or "").strip()
    if not description:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="image_not_describable"
        )

    embedder = _ensure_embedder()
    _ensure_qdrant_collection(collection, vector_size=embedder.dim)
    vector = embedder.embed_one(description)
    kind_list = [k for k in (kinds.split(",") if kinds else []) if k.strip()]
    extra_filter = _rag_extra_filter(project_id=project_id, kinds=kind_list or None)
    try:
        raw_hits = qc.search(
            collection=collection,
            tenant_id=auth.tenant_id or "",
            query_vector=vector,
            limit=max(1, min(limit, 50)),
            extra_filter=extra_filter,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("qdrant_search_failed: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"qdrant_search_failed: {exc}",
        ) from exc
    hits = _raw_to_hits(raw_hits)
    elapsed = (time.perf_counter() - started) * 1000.0
    logger.info(
        "rag_query_by_image tenant=%s mime=%s hits=%d ms=%.1f",
        auth.tenant_id,
        mime,
        len(hits),
        elapsed,
    )
    get_usage_logger().record(
        make_event(
            name="rag.query_by_image",
            tenant_id=auth.tenant_id,
            user_subject=auth.subject,
            request_type="query",
            status="ok",
            latency_ms=elapsed,
            input_tokens=estimate_token_count(description),
            output_tokens=len(hits),
            model_version=f"gemini-vision+{settings.embedding_backend}",
            metadata={"hits": len(hits), "kind": "image_query"},
        )
    )
    return ImageQueryResponse(description=description, hits=hits, elapsed_ms=elapsed)


@router.get("/documents")
@observe(name="rag.documents")
def list_documents(
    request: Request,
    rag: RAGAuth = Depends(rag_action_dep("query")),
) -> dict[str, Any]:
    """Document inventory for the caller's tenant — groups stored chunks by
    ``doc_id``. Powers the admin RAG page so a reload shows the real indexed
    corpus (not just this session's uploads). Tolerant of a missing
    collection / Qdrant outage → empty inventory rather than 5xx.

    Project-scoped via ``X-Project-Id`` — consistent with the query path — so a
    project workspace lists only its own documents (no header ⇒ tenant-wide).
    """
    auth = rag.auth
    collection = _tenant_collection(auth)
    project_id = _active_project(request, auth)
    try:
        raw = qc.list_documents(
            collection=collection,
            tenant_id=auth.tenant_id or "",
            project_id=project_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("rag_documents_unavailable: %s", exc)
        raw = []
    # A document is only searchable by the model that embedded it. Change the
    # embedding backend and every older document is still here, still listed,
    # still counted — and unreachable by any question, with no error anywhere to
    # say so. Marking them is what makes them fixable: re-uploading a stale
    # document re-embeds it.
    current_model = model_id_of(_ensure_embedder())
    documents = [
        {
            "id": d["doc_id"],
            "filename": d["filename"] or d["doc_id"],
            "chunks": int(d["chunks"]),
            "size_bytes": int(d["bytes"]),
            "embed_model": d.get("embed_model") or "",
            "stale": bool(d.get("embed_model") != current_model),
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
        "embed_model": current_model,
        "documents": documents,
        "doc_count": len(documents),
        "stale_count": sum(1 for d in documents if d["stale"]),
        "chunk_count": sum(d["chunks"] for d in documents),
        "total_bytes": sum(d["size_bytes"] for d in documents),
    }


@router.delete("/documents/{doc_id}")
@observe(name="rag.delete_document")
async def delete_document(
    request: Request,
    doc_id: str,
    rag: RAGAuth = Depends(rag_action_dep("ingest")),
) -> dict[str, Any]:
    """Delete a document (all its chunks) from the caller's tenant collection.

    Lets a tenant remove uploaded documents from their own collection.
    Tenant-scoped via the Qdrant filter, so a caller can only delete their own
    documents. Project-scoped via ``X-Project-Id`` (consistent with the
    list/query paths) so a project workspace cannot delete a sibling project's
    document. Idempotent: deleting an unknown doc_id returns deleted=0.

    Async so the GraphRAG purge can ``await`` the module-singleton Neo4j async
    driver on the SAME loop it was bound to (a sync route + ``asyncio.run`` hits
    a "future attached to a different loop" error). The sync Qdrant delete runs
    in a worker thread.
    """
    import asyncio

    auth = rag.auth
    collection = _tenant_collection(auth)
    if not (doc_id or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "doc_id_required")
    project_id = _active_project(request, auth)
    try:
        removed = await asyncio.to_thread(
            qc.delete_document,
            collection=collection,
            tenant_id=auth.tenant_id or "",
            doc_id=doc_id,
            project_id=project_id,
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
    # GraphRAG consistency — a deleted document must not leave orphan chunks /
    # entities behind in the knowledge graph (they would otherwise surface in
    # graph-rag answers and bloat Neo4j). Best-effort + flag-gated: a missing or
    # unreachable Neo4j never fails the (already-committed) Qdrant delete. Only
    # purge when the Qdrant delete actually removed chunks — a project-scoped
    # no-op delete must not purge another project's graph.
    graph_purged: bool | None = None
    if settings.graphrag_enabled and removed > 0:
        try:
            from app.graph_rag.store import purge_doc_graph
            from app.integrations.neo4j_client import Neo4jClient

            await purge_doc_graph(
                Neo4jClient(), tenant_id=auth.tenant_id or "", doc_id=doc_id
            )
            graph_purged = True
        except Exception as exc:  # noqa: BLE001 — graph purge is best-effort
            logger.warning("rag_delete_graph_purge_failed doc=%s: %s", doc_id, exc)
            graph_purged = False
    return {"doc_id": doc_id, "deleted": removed, "graph_purged": graph_purged}
