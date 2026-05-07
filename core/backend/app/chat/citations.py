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

    try:
        from app.rag.query import query as rag_query  # local import: lazy
    except Exception as exc:  # pragma: no cover — import-time RAG missing
        logger.debug("rag import failed, skipping citations: %s", exc)
        return []

    try:
        rows = await rag_query(query, project_filter=project, top_k=top_k)
    except Exception as exc:
        logger.info("rag query failed (no citations): %s", exc)
        return []

    citations: list[ChatCitation] = []
    for idx, row in enumerate(rows):
        if "error" in row:
            continue
        file_path = row.get("file") or ""
        chunk_idx = row.get("chunk_idx", idx)
        chunk_hash = row.get("hash") or ""
        rid = (
            f"{row.get('project') or 'default'}:{file_path}:"
            f"{chunk_idx}:{chunk_hash}"
        )
        score = row.get("score")
        if score is not None:
            score = max(0.0, min(1.0, float(score)))
        citations.append(
            ChatCitation(
                chunk_id=rid,
                source=file_path or row.get("project") or "",
                relevance_score=score,
                excerpt=(row.get("snippet") or "")[:200],
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
