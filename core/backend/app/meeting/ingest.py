# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Shared meeting-ingestion tail: turn a transcription *result* into a finished
Meeting + segments + RAG index.

One codepath, two callers:

  - `POST /v1/meetings/upload` transcribes an uploaded audio file, then hands
    the result here.
  - live capture (`app/meeting/capture_service`) receives a recording the bot
    already transcribed, and hands that result here.

Keeping the persist-and-index step in one place is deliberate: the meeting RAG
autoindex is exactly the kind of logic that rots when it is copied — a fix to
how a transcript reaches the vector store has to land on every surface that
writes one, or a meeting captured live becomes unanswerable while an uploaded
one works. There is one writer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from sqlmodel import Session, select

from app.config import settings
from app.db.models import Meeting, MeetingSegment
from app.db.session import get_engine
from app.meeting.quality import speech_verdict

logger = logging.getLogger(__name__)


def finalize_meeting(
    *,
    meeting_id: int,
    result: Dict[str, Any],
    filename: str,
    uploader_email: str,
) -> Tuple[Any, Meeting, List[MeetingSegment]]:
    """Finalize a *pending* Meeting row from a transcription result.

    Writes duration/speakers/summary, persists the segments, marks the row
    `done` with a speech-quality note, and best-effort indexes the transcript
    into the tenant's RAG store (only when there is real speech — hallucinated
    room-tone text in the vector store is worse than a missing meeting).

    Returns `(verdict, meeting_row, segments)` — the row and segments are the
    just-loaded (detached) objects, ready to serialize. Raises RuntimeError if
    the row vanished mid-flight.
    """
    # Lazy import: the RAG/serialize helpers live in the meetings API module,
    # which must be free to import this one. Importing at call time keeps the
    # dependency one-way and dodges a circular import at startup.
    from app.api.meetings import (
        _autoindex_meeting_rag,
        _doc_id,
    )

    verdict = speech_verdict(
        float(result.get("duration_sec", 0.0)), result.get("segments", [])
    )
    if not verdict.has_speech:
        logger.warning(
            "meeting_no_speech meeting=%s duration=%.0fs chars=%d cpm=%.1f",
            meeting_id,
            verdict.duration_sec,
            verdict.chars,
            verdict.chars_per_minute,
        )

    with Session(get_engine()) as db:
        row = db.get(Meeting, meeting_id)
        if row is None:
            raise RuntimeError(f"meeting_disappeared:{meeting_id}")
        row.duration_sec = float(result.get("duration_sec", 0.0))
        row.speaker_count = len(result.get("speakers", []))
        row.summary = str(result.get("summary", ""))[:4096]
        row.status = "done"
        row.quality_note = verdict.reason[:512]
        row.completed_at = datetime.now(timezone.utc)
        db.add(row)
        for seg in result.get("segments", []):
            db.add(
                MeetingSegment(
                    meeting_id=meeting_id,
                    speaker_id=seg["speaker_id"],
                    start_sec=float(seg.get("start", 0.0)),
                    end_sec=float(seg.get("end", 0.0)),
                    text=seg.get("text", ""),
                )
            )
        db.commit()

        segments = list(
            db.execute(
                select(MeetingSegment)
                .where(MeetingSegment.meeting_id == meeting_id)
                .order_by(MeetingSegment.start_sec)
            ).scalars()
        )
        meeting_row = db.get(Meeting, meeting_id)
        if meeting_row is None:
            raise RuntimeError(f"meeting_disappeared:{meeting_id}")

    if settings.meeting_rag_autoindex and verdict.has_speech:
        try:
            n = _autoindex_meeting_rag(
                doc_id=_doc_id(meeting_row),
                title=filename,
                uploader_email=uploader_email,
                result=result,
            )
            logger.info("meeting_rag_autoindex meeting=%s chunks=%d", meeting_id, n)
        except Exception as exc:  # noqa: BLE001 — best-effort, never fail ingest
            logger.warning(
                "meeting_rag_autoindex_failed meeting=%s err=%s", meeting_id, exc
            )

    return verdict, meeting_row, segments
