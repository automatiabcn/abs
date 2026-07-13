# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-030 — Meeting transcript → RAG indexing helper.

Converts a transcript into RAG chunks (per-segment) and dispatches them to the
T-009 Qdrant wrapper under the caller's tenant. Retention budget exposed via
`settings.meeting_retention_days` so a periodic cleaner (out-of-scope here)
can purge older meetings.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from app.meeting.transcribe import Transcript

logger = logging.getLogger(__name__)

__all__ = ["MeetingRAGIndexer", "build_chunks_from_transcript"]


def build_chunks_from_transcript(
    transcript: Transcript,
    *,
    meeting_id: str,
    title: str = "",
    tenant_id: str,
    extra_metadata: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    now = int(time.time())
    chunks: list[dict[str, Any]] = []
    for idx, seg in enumerate(transcript.segments):
        if not seg.text.strip():
            continue
        seg_text = f"[{seg.speaker}] {seg.text.strip()}"
        chunks.append(
            {
                "id": f"{meeting_id}-seg-{idx:04d}",
                "text": seg_text,
                "payload": {
                    # `text` lives in the payload too (mirrors the doc-ingest
                    # path) so RAG query/search returns the snippet directly.
                    "text": seg_text,
                    "tenant_id": tenant_id,
                    "doc_id": meeting_id,
                    "chunk_id": f"{meeting_id}-seg-{idx:04d}",
                    "seq": idx,
                    "speaker": seg.speaker,
                    "start": seg.start,
                    "end": seg.end,
                    "title": title,
                    "kind": "meeting_transcript",
                    "created_at": now,
                    **(extra_metadata or {}),
                },
            }
        )
    return chunks


class MeetingRAGIndexer:
    """Tenant-safe transcript → vector index dispatcher."""

    def __init__(
        self,
        *,
        embed_fn: Callable[[list[str]], list[list[float]]],
        upsert_fn: Callable[..., int],
        ensure_fn: Callable[..., None] | None = None,
        collection: str = "abs_meetings",
    ) -> None:
        self._embed = embed_fn
        self._upsert = upsert_fn
        self._ensure = ensure_fn
        self.collection = collection

    def index(
        self,
        transcript: Transcript,
        *,
        meeting_id: str,
        title: str,
        tenant_id: str,
        extra_metadata: dict[str, str] | None = None,
    ) -> int:
        if not tenant_id:
            raise ValueError("tenant_id required for meeting RAG indexing")
        if self._ensure is not None:
            self._ensure(self.collection)
        chunks = build_chunks_from_transcript(
            transcript,
            meeting_id=meeting_id,
            title=title,
            tenant_id=tenant_id,
            extra_metadata=extra_metadata,
        )
        if not chunks:
            return 0
        vectors = self._embed([c["text"] for c in chunks])
        points = [
            {"id": c["id"], "vector": v, "payload": c["payload"]}
            for c, v in zip(chunks, vectors)
        ]
        n = self._upsert(collection=self.collection, tenant_id=tenant_id, points=points)
        logger.info(
            "meeting_index meeting=%s tenant=%s chunks=%d",
            meeting_id,
            tenant_id,
            n,
        )
        return n
