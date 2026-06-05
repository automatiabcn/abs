# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Q12 / Brief 3 R1 — RAG citation retrieval + prompt-block helpers.

Used by the chat backend to retrieve top-K chunks from the per-tenant
Chroma collection, build a `[1] {chunk}\\n[2] {chunk}\\n…` block to
inject into the prompt, and return a structured `ChatCitation` list that
the SSE `meta` event ships back to the client (and the message
persistence layer stores in `tool_calls`).
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ChatCitation(BaseModel):
    """Single source chunk surfaced under an assistant message.

    `chunk_id` is the Chroma id (project:file:idx:hash). `excerpt` is
    capped at 200 chars to keep SSE frames small. `relevance_score` is
    the cosine-similarity-derived score from `app.rag.query.query`,
    bounded 0–1 (None when the backend cannot report it).
    """

    chunk_id: str
    source: str = ""
    relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    excerpt: str = Field(default="", max_length=200)
    page: int | None = None


async def retrieve_citations(
    query: str,
    *,
    project: str | None = None,
    top_k: int = 5,
) -> list[ChatCitation]:
    """Run a tenant-scoped RAG search and return up-to-K citations.

    Returns an empty list (NEVER fabricates) if RAG is unavailable, the
    embedder errors, or no matches cross the relevance floor. The chat
    handler is responsible for deciding what to do when the list is
    empty — never invent citations downstream.
    """
    if not query or not query.strip():
        return []

    # "Chat with your documents" must search the SAME tenant Qdrant store the
    # panel uploads into (/v1/rag/ingest*), NOT the operator Chroma KB — else
    # panel-uploaded company docs never produce citations (they were silently
    # invisible to chat). `project` is the tenant_id (e.g. "default").
    tenant = (project or "").strip()
    if not tenant:
        return []

    def _search() -> list[dict]:
        # Run the embed + Qdrant search on a worker thread: the Cohere
        # embedder calls asyncio.run() internally, which crashes inside the
        # async SSE handler's running event loop (same trap that 500'd
        # /ingest-file). asyncio.to_thread gives it a loop-free context.
        from app.config import settings
        from app.rag import qdrant_client as qc
        from app.rag.embedding_bge import get_embedder

        embedder = get_embedder()
        collection = settings.qdrant_default_collection
        qc.ensure_collection(collection, vector_size=embedder.dim)
        vector = embedder.embed_one(query)
        return qc.search(
            collection=collection,
            tenant_id=tenant,
            query_vector=vector,
            limit=top_k,
        )

    try:
        import asyncio

        hits = await asyncio.to_thread(_search)
    except Exception as exc:  # noqa: BLE001 — never break chat over citations
        logger.info("citation qdrant search failed (no citations): %s", exc)
        return []

    citations: list[ChatCitation] = []
    for idx, hit in enumerate(hits):
        payload = hit.get("payload") or {}
        source = str(
            payload.get("filename")
            or payload.get("doc_id")
            or (payload.get("metadata") or {}).get("filename")
            or ""
        )
        score = hit.get("score")
        if score is not None:
            score = max(0.0, min(1.0, float(score)))
        page = payload.get("page") or (payload.get("metadata") or {}).get("page")
        citations.append(
            ChatCitation(
                chunk_id=str(hit.get("id") or f"{tenant}:{idx}"),
                source=source,
                relevance_score=score,
                excerpt=str(payload.get("text") or "")[:200],
                page=int(page) if isinstance(page, (int, str)) and str(page).isdigit() else None,
            )
        )
    return citations


def build_citation_prompt_block(
    citations: Sequence[ChatCitation],
    *,
    user_message: str,
) -> str:
    """Render the [1] / [2] / … chunk block + system reminder.

    Returns the *complete* prompt the cascade should see. When no
    citations are passed, the original message is returned unchanged so
    the model is not nudged toward hallucinated brackets.
    """
    if not citations:
        return user_message

    lines: list[str] = []
    lines.append(
        "You are answering using the project knowledge base. Cite sources "
        "inline as [1], [2], etc. matching the numbered chunks below. "
        "If the chunks do not answer the question, say so plainly — never "
        "invent a citation."
    )
    lines.append("")
    lines.append("# Source chunks")
    for n, c in enumerate(citations, start=1):
        src = c.source or c.chunk_id
        lines.append(f"[{n}] ({src})")
        if c.excerpt:
            lines.append(c.excerpt.strip())
        lines.append("")
    lines.append("# User question")
    lines.append(user_message)
    return "\n".join(lines)


def serialise_citations(
    citations: Iterable[ChatCitation],
) -> list[dict]:
    """JSON-safe shape for SSE + DB persistence."""
    return [c.model_dump() for c in citations]


__all__ = [
    "ChatCitation",
    "build_citation_prompt_block",
    "retrieve_citations",
    "serialise_citations",
]
