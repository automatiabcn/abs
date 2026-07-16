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
from app.meeting.ingest import finalize_meeting
from app.meeting.quality import audio_fingerprint
from app.observability.audit import emit_event
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
    *, doc_id: str, title: str, uploader_email: str, result: Dict[str, Any]
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
    from app.rag.embedding_bge import get_embedder, model_id_of

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
        meeting_id=doc_id,
        title=title,
        tenant_id=tenant,
        # Same stamp the document ingest writes: which model made these vectors.
        extra_metadata={"embed_model": model_id_of(embedder)},
    )


def _suffix(filename: str | None) -> str:
    if not filename:
        return ".bin"
    suffix = Path(filename).suffix
    return suffix if suffix else ".bin"


def _doc_id(meeting: Meeting) -> str:
    """What this meeting is called in the vector store.

    It used to be `meeting-<id>` — the database's autoincrement counter. The
    vector store outlives the database: restore last week's backup, or reset a
    development install, and the counter starts again over chunks that are still
    there. Meeting 2 then inherits the chunks of whatever meeting 2 used to be —
    the panel shows a green "indexed" tick for a recording it has never indexed,
    and a question about it is answered out of somebody else's conversation, with
    a citation. The name of the wrong meeting, on a confident answer.

    The recording's own SHA-256 is already computed (it is how the same file
    uploaded twice stays one meeting) and it does not restart at 1. Chunks are
    filed under it now, so the store and the database can no longer disagree about
    which recording they are talking about.
    """
    sha = (meeting.audio_sha256 or "").strip()
    return f"meeting-{sha[:32]}" if sha else f"meeting-{meeting.id}"


def _legacy_doc_id(meeting: Meeting) -> str:
    """What it was called before — chunks written by an earlier version."""
    return f"meeting-{meeting.id}"


def _indexed_chunk_count(meeting: Meeting) -> int:
    """How many chunks of this meeting are in the vector store, right now.

    `indexed` used to be `status == "done" and not quality_note` — an inference
    about transcription, presented as a fact about indexing. The autoindex call
    is best-effort and swallows its own failures (rightly: a Qdrant hiccup must
    not lose a transcript that is already saved), so the two can disagree, and
    when they did the panel showed a green tick over an empty index. Nobody
    finds out until a question about the meeting quietly comes back unanswered.
    Ask the store instead.
    """
    from app.rag import qdrant_client as qc
    from app.rag.embedding_bge import get_embedder, model_id_of

    def _count(doc_id: str) -> int:
        return qc.count_document(
            collection=settings.qdrant_default_collection,
            tenant_id=meeting.tenant_slug or DEFAULT_TENANT_SLUG,
            doc_id=doc_id,
            # Chunks left behind by a previous embedding backend are present but
            # unfindable — they do not count, and re-uploading the file rebuilds
            # them.
            embed_model=model_id_of(get_embedder()),
        )

    try:
        found = _count(_doc_id(meeting))
        if found:
            return found
        # Nothing under the recording's own name. It may simply have been indexed
        # by an earlier version, which filed it under the database's counter — so
        # look there too, and keep the green tick a customer's existing meetings
        # have earned.
        #
        # Except when the meeting was flagged: a recording with no speech in it is
        # never indexed, by construction, so anything sitting under its old number
        # belongs to a different recording — the exact confusion this is here to
        # stop. Asking would only let a stale chunk answer for it.
        if meeting.quality_note:
            return 0
        return _count(_legacy_doc_id(meeting))
    except Exception as exc:  # noqa: BLE001 — an unreachable store is not indexed
        logger.warning("meeting_index_count_failed meeting=%s err=%s", meeting.id, exc)
        return 0


def _serialize(meeting: Meeting, segments: List[MeetingSegment]) -> Dict[str, Any]:
    speaker_seen: Dict[str, int] = {}
    speakers: List[Dict[str, str]] = []
    seg_payload: List[Dict[str, Any]] = []
    for seg in segments:
        if seg.speaker_id not in speaker_seen:
            speaker_seen[seg.speaker_id] = len(speakers) + 1
            speakers.append(
                {
                    "id": seg.speaker_id,
                    "name": f"Speaker {speaker_seen[seg.speaker_id]}",
                }
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
        "indexed": _indexed_chunk_count(meeting) > 0,
        "speakers": speakers,
        "segments": seg_payload,
        "created_at": meeting.created_at.isoformat(),
        "completed_at": meeting.completed_at.isoformat()
        if meeting.completed_at
        else None,
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
                    "indexed": _indexed_chunk_count(meeting) > 0,
                    "created_at": meeting.created_at.isoformat(),
                    "completed_at": meeting.completed_at.isoformat()
                    if meeting.completed_at
                    else None,
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
            # Deduplication protects the transcript, and it used to protect the
            # gap as well: if the chunks never made it into the vector store —
            # the autoindex failed, or the operator has since switched embedding
            # backend, which leaves every old vector pointing into a space
            # nothing searches any more — then re-uploading the file was the
            # obvious remedy and it did nothing at all, because the dedup check
            # short-circuits before indexing. The meeting stayed unanswerable
            # forever, showing a green tick. So: transcription is still never
            # repeated (that is the expensive part), but a missing index is
            # rebuilt from the segments already in SQL. Chunk ids are
            # deterministic, so a healthy meeting re-indexes to exactly the same
            # points — one meeting, one copy, which is what T3 asks for.
            if (
                not _indexed_chunk_count(seen)
                and seen.status == "done"
                and not seen.quality_note
            ):
                try:
                    n = _autoindex_meeting_rag(
                        doc_id=_doc_id(seen),
                        title=seen.filename,
                        uploader_email=uploader_email,
                        result={
                            "language": "auto",
                            "duration_sec": seen.duration_sec,
                            "segments": [
                                {
                                    "speaker_id": s.speaker_id,
                                    "start": s.start_sec,
                                    "end": s.end_sec,
                                    "text": s.text,
                                }
                                for s in segments
                            ],
                        },
                    )
                    logger.info("meeting_rag_reindex meeting=%s chunks=%d", seen.id, n)
                except Exception as exc:  # noqa: BLE001 — never fail the upload
                    logger.warning(
                        "meeting_rag_reindex_failed meeting=%s err=%s", seen.id, exc
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
            raise HTTPException(503, f"whisperx_unavailable: {exc}") from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    # Persist segments, finalize the meeting, and index the transcript — the
    # shared ingestion tail, one writer for both upload and live capture. The
    # dead-microphone guard (two hours of audio, four hallucinated sentences)
    # and the never-index-speechless-audio rule live inside it.
    try:
        _verdict, meeting_row, segments = finalize_meeting(
            meeting_id=meeting_id,
            result=result,
            filename=filename,
            uploader_email=uploader_email,
        )
    except RuntimeError as exc:
        raise HTTPException(500, "meeting_disappeared") from exc

    try:
        feature_usage_service.increment("audio_upload", actor_email=uploader_email)
    except Exception:
        pass

    # Serialised last, on purpose: `indexed` is read back from the vector store,
    # and the indexing happened inside finalize_meeting. Building the response
    # before the write would report `indexed: false` on every successful upload.
    return _serialize(meeting_row, segments)


@router.delete("/{meeting_id}")
async def delete_meeting(
    meeting_id: int, admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    """Delete a recording: the transcript, the segments, and the chunks.

    There was no way to do this. A person could upload a recording of a private
    conversation — the wrong file, the wrong meeting, a client who has since asked
    to be forgotten — and the product would transcribe it, index it, and answer
    questions out of it forever. An uploaded document can be deleted
    (`/v1/rag/documents/{doc_id}`); the recording of an actual conversation could
    not, which is the wrong way round.

    Everything, or it does not count: the chunks go first, because a transcript
    the search index has outlived is a transcript that still answers questions.
    (The audio itself is never persisted — it is transcribed from a temp file that
    is unlinked in a `finally`.)
    """
    tenant = _admin_tenant(admin)
    with Session(get_engine()) as db:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or meeting.tenant_slug != tenant:
            raise HTTPException(404, "meeting_not_found")
        doc_ids = {_doc_id(meeting), _legacy_doc_id(meeting)}
        filename = meeting.filename

    from app.rag import qdrant_client as qc

    removed = 0
    for doc_id in doc_ids:
        try:
            removed += qc.delete_document(
                collection=settings.qdrant_default_collection,
                tenant_id=tenant,
                doc_id=doc_id,
            )
        except Exception as exc:  # noqa: BLE001
            # The one failure that must not be quiet. If the chunks survive, the
            # meeting is still answerable, and telling the operator it is gone
            # would be the most damaging thing this endpoint could do.
            logger.error(
                "meeting_delete_chunks_failed meeting=%s doc=%s err=%s",
                meeting_id,
                doc_id,
                exc,
            )
            raise HTTPException(
                503,
                "the recording is still in the knowledge base and was not deleted — "
                "the vector store did not answer. Nothing has been removed.",
            ) from exc

    with Session(get_engine()) as db:
        for seg in db.execute(
            select(MeetingSegment).where(MeetingSegment.meeting_id == meeting_id)
        ).scalars():
            db.delete(seg)
        row = db.get(Meeting, meeting_id)
        if row is not None:
            db.delete(row)
        db.commit()

    # A recording of a conversation was destroyed on this server. Who, and when,
    # is a question that gets asked on a bad day and needs an answer.
    emit_event(
        None,
        action="meeting.delete",
        outcome="success",
        resource_type="meeting",
        resource_id=str(meeting_id),
        user_id=str(admin.get("sub") or ""),
        tenant_id=tenant,
        chunks_removed=removed,
    )
    logger.info(
        "meeting_deleted meeting=%s file=%s chunks=%d by=%s",
        meeting_id,
        filename,
        removed,
        admin.get("sub"),
    )
    return {"deleted": True, "id": meeting_id, "chunks_removed": removed}


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
