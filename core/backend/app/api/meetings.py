# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""S20.4 — /v1/meetings: persistent meeting upload + retrieval.

  GET  /v1/meetings              → 50 most recent for tenant
  POST /v1/meetings/upload       → 201 with full meeting payload
  GET  /v1/meetings/{id}         → 200 with segments + speakers

`tenant_slug` derives from the panel session's bootstrap admin (single-tenant
self-host). When multi-tenant lands we read it from the JWT `tnt` claim.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from app.api.auth import current_admin
from app.config import settings
from app.db.models import Meeting, MeetingSegment
from app.db.session import get_engine
from app.meeting.quality import audio_fingerprint, speech_verdict
from app.services import feature_usage as feature_usage_service
from app.services.transcribe import (
    WhisperXUnavailableError,
    transcribe_path,
)

router = APIRouter(prefix="/v1/meetings", tags=["meetings"])
logger = logging.getLogger(__name__)


MAX_UPLOAD_BYTES = 250 * 1024 * 1024
DEFAULT_TENANT_SLUG = "default"


def _admin_tenant(admin: dict) -> str:
    """Resolve the request admin's tenant (multi-tenant aware).

    Mirrors the tenant the panel RAG ingest + autoindex resolve, so a meeting,
    its RAG chunks and its graph all land under the same tenant. Falls back to
    the single-tenant default so self-host (tenant=default) behaviour
    is unchanged — and so the row is writable under the RLS policy (0019), whose
    GUC the tenant-context middleware pins from this same admin session.
    """
    from app.api.chat import _resolve_tenant

    try:
        return _resolve_tenant(str(admin.get("sub") or "")) or DEFAULT_TENANT_SLUG
    except Exception:  # noqa: BLE001 — never block on tenant resolution
        return DEFAULT_TENANT_SLUG


def _autoindex_meeting_rag(
    *, meeting_id: int, title: str, uploader_email: str, result: Dict[str, Any]
) -> int:
    """Best-effort: index a finished transcript into the tenant's Qdrant
    document store so the meeting is answerable from panel RAG + MCP rag_query.

    Indexes into `settings.qdrant_default_collection` under the SAME tenant the
    panel RAG ingest resolves (`_resolve_tenant`) so all three surfaces share
    one corpus. Never raises — a RAG/embedder/Qdrant hiccup must not fail the
    upload (the transcript is already persisted in SQL).
    """
    import uuid as _uuid

    from qdrant_client.models import PointStruct

    from app.api.chat import _resolve_tenant
    from app.meeting.rag_index import MeetingRAGIndexer
    from app.meeting.transcribe import Transcript, TranscriptSegment
    from app.rag import qdrant_client as qc
    from app.rag.embedding_bge import get_embedder

    tenant = _resolve_tenant(uploader_email) or DEFAULT_TENANT_SLUG
    segments = [
        TranscriptSegment(
            speaker=str(seg.get("speaker_id", "speaker")),
            start=float(seg.get("start", 0.0)),
            end=float(seg.get("end", 0.0)),
            text=str(seg.get("text", "")),
        )
        for seg in result.get("segments", [])
    ]
    transcript = Transcript(
        language=str(result.get("language", "auto")),
        duration=float(result.get("duration_sec", 0.0)),
        segments=segments,
        backend=str(result.get("backend", "whisperx")),
    )

    embedder = get_embedder()

    def _upsert(*, collection: str, tenant_id: str, points: list) -> int:
        # Qdrant point IDs must be int/UUID; meeting chunk ids are strings
        # (`<meeting>-seg-0001`) → map deterministically to UUID5, keep the
        # original chunk_id in the payload for traceability.
        structs = [
            PointStruct(
                id=str(_uuid.uuid5(_uuid.NAMESPACE_URL, str(p["id"]))),
                vector=p["vector"],
                payload=p["payload"],
            )
            for p in points
        ]
        return qc.upsert_points(
            collection=collection, tenant_id=tenant_id, points=structs
        )

    indexer = MeetingRAGIndexer(
        embed_fn=embedder.embed,
        upsert_fn=_upsert,
        ensure_fn=lambda c: qc.ensure_collection(c, vector_size=embedder.dim),
        collection=settings.qdrant_default_collection,
    )
    return indexer.index(
        transcript,
        meeting_id=f"meeting-{meeting_id}",
        title=title,
        tenant_id=tenant,
    )


def _suffix(filename: str | None) -> str:
    if not filename:
        return ".bin"
    suffix = Path(filename).suffix
    return suffix if suffix else ".bin"


def _serialize(meeting: Meeting, segments: List[MeetingSegment]) -> Dict[str, Any]:
    speaker_seen: Dict[str, int] = {}
    speakers: List[Dict[str, str]] = []
    seg_payload: List[Dict[str, Any]] = []
    for seg in segments:
        if seg.speaker_id not in speaker_seen:
            speaker_seen[seg.speaker_id] = len(speakers) + 1
            speakers.append(
                {"id": seg.speaker_id, "name": f"Speaker {speaker_seen[seg.speaker_id]}"}
            )
        seg_payload.append(
            {
                "speaker_id": seg.speaker_id,
                "start": seg.start_sec,
                "end": seg.end_sec,
                "text": seg.text,
            }
        )
    return {
        "id": meeting.id,
        "filename": meeting.filename,
        "duration_sec": meeting.duration_sec,
        "speaker_count": meeting.speaker_count,
        "status": meeting.status,
        "summary": meeting.summary,
        "error_message": meeting.error_message,
        # Non-empty when the recording transcribed but holds no usable speech.
        # The panel shows this sentence instead of a silent green tick.
        "quality_note": meeting.quality_note,
        "indexed": meeting.status == "done" and not meeting.quality_note,
        "speakers": speakers,
        "segments": seg_payload,
        "created_at": meeting.created_at.isoformat(),
        "completed_at": meeting.completed_at.isoformat() if meeting.completed_at else None,
    }


@router.get("")
async def list_meetings(admin: dict = Depends(current_admin)) -> Dict[str, Any]:
    with Session(get_engine()) as db:
        rows = list(
            db.execute(
                select(Meeting)
                .where(Meeting.tenant_slug == _admin_tenant(admin))
                .order_by(Meeting.created_at.desc())
                .limit(50)
            ).scalars()
        )
        out: List[Dict[str, Any]] = []
        for meeting in rows:
            out.append(
                {
                    "id": meeting.id,
                    "filename": meeting.filename,
                    "duration_sec": meeting.duration_sec,
                    "speaker_count": meeting.speaker_count,
                    "status": meeting.status,
                    "summary": meeting.summary,
                    "quality_note": meeting.quality_note,
                    "indexed": meeting.status == "done" and not meeting.quality_note,
                    "created_at": meeting.created_at.isoformat(),
                    "completed_at": meeting.completed_at.isoformat() if meeting.completed_at else None,
                }
            )
    return {"meetings": out, "count": len(out)}


@router.post("/upload", status_code=201)
async def upload_meeting(
    audio: UploadFile = File(...),
    admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    raw = await audio.read()
    if not raw:
        raise HTTPException(400, "empty_upload")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "audio_too_large")

    uploader_email = admin.get("sub", "admin@local")
    filename = audio.filename or f"meeting-{uuid.uuid4().hex}.bin"
    tenant_slug = _admin_tenant(admin)
    fingerprint = audio_fingerprint(raw)

    # Have we already transcribed exactly these bytes? Answer before spending a
    # GPU minute on them — and before putting a second copy of every passage in
    # the vector store, where duplicates read as sources agreeing.
    with Session(get_engine()) as db:
        seen = db.exec(
            select(Meeting)
            .where(Meeting.tenant_slug == tenant_slug)
            .where(Meeting.audio_sha256 == fingerprint)
            .where(Meeting.status == "done")
            .order_by(Meeting.created_at)
        ).first()
        if seen is not None:
            segments = list(
                db.exec(
                    select(MeetingSegment)
                    .where(MeetingSegment.meeting_id == seen.id)
                    .order_by(MeetingSegment.start_sec)
                )
            )
            logger.info(
                "meeting_upload_duplicate tenant=%s meeting=%s sha=%s",
                tenant_slug,
                seen.id,
                fingerprint[:12],
            )
            payload = _serialize(seen, segments)
            # The upload succeeded and the meeting exists; it simply already
            # existed. Saying so is more useful than a 409 the panel would have
            # to translate back into "here is your meeting".
            payload["duplicate_of"] = seen.id
            return payload

    meeting = Meeting(
        tenant_slug=tenant_slug,
        uploader_email=uploader_email,
        filename=filename,
        audio_sha256=fingerprint,
        status="pending",
    )

    with Session(get_engine()) as db:
        db.add(meeting)
        db.commit()
        db.refresh(meeting)
        meeting_id = meeting.id

    tmp_path = Path(tempfile.gettempdir()) / (
        f"abs-meeting-{meeting_id}{_suffix(filename)}"
    )
    try:
        tmp_path.write_bytes(raw)
        try:
            result = await transcribe_path(tmp_path)
        except WhisperXUnavailableError as exc:
            with Session(get_engine()) as db:
                row = db.get(Meeting, meeting_id)
                if row is not None:
                    row.status = "error"
                    row.error_message = f"whisperx_unavailable: {exc}"[:512]
                    row.completed_at = datetime.now(timezone.utc)
                    db.add(row)
                    db.commit()
            raise HTTPException(
                503, f"whisperx_unavailable: {exc}"
            ) from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    # Two hours of audio that yielded four sentences was not a quiet meeting —
    # it was a dead microphone, and what came back is the model hallucinating
    # over room tone. It transcribed without erroring, so nothing else in this
    # pipeline would have caught it.
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

    # Persist segments + finalize meeting.
    with Session(get_engine()) as db:
        row = db.get(Meeting, meeting_id)
        if row is None:
            raise HTTPException(500, "meeting_disappeared")
        row.duration_sec = float(result.get("duration_sec", 0.0))
        row.speaker_count = len(result.get("speakers", []))
        row.summary = result.get("summary", "")[:4096]
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
            raise HTTPException(500, "meeting_disappeared")
        payload = _serialize(meeting_row, segments)

    try:
        feature_usage_service.increment(
            "audio_upload", actor_email=uploader_email
        )
    except Exception:
        pass

    # A recording with no speech in it is kept — the operator can see for
    # themselves what came back — but it is not indexed. Hallucinated text in
    # the vector store is worse than a missing meeting: it answers questions.
    if settings.meeting_rag_autoindex and verdict.has_speech:
        try:
            n = _autoindex_meeting_rag(
                meeting_id=meeting_id,
                title=filename,
                uploader_email=uploader_email,
                result=result,
            )
            logger.info("meeting_rag_autoindex meeting=%s chunks=%d", meeting_id, n)
        except Exception as exc:  # noqa: BLE001 — best-effort, never fail upload
            logger.warning(
                "meeting_rag_autoindex_failed meeting=%s err=%s", meeting_id, exc
            )

    return payload


@router.get("/{meeting_id}")
async def get_meeting(
    meeting_id: int, admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    with Session(get_engine()) as db:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or meeting.tenant_slug != _admin_tenant(admin):
            raise HTTPException(404, "meeting_not_found")
        segments = list(
            db.execute(
                select(MeetingSegment)
                .where(MeetingSegment.meeting_id == meeting_id)
                .order_by(MeetingSegment.start_sec)
            ).scalars()
        )
        return _serialize(meeting, segments)
