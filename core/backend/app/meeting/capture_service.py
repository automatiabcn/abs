# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Live-capture orchestration — the service behind the 'auto-capture' surface.

A person schedules a meeting for capture (a pasted link now; a connected
calendar later). This layer:

  - creates the persistent CaptureJob,
  - asks the meeting bot (app/meeting/bot_recall) to join and record,
  - maps the bot's real lifecycle onto the job's honest status, and
  - (slice 2) feeds the finished recording into the same
    transcribe→Meeting→RAG pipeline an upload uses.

Honesty rule: the status is only ever what the *bot backend* reports. On the
mock backend — the default when no recorder side-car or Recall.ai key is
configured — a job never advances past `scheduled`, and the surface says so,
rather than inventing a recording or a Meeting.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.db.models import CaptureJob, Meeting
from app.db.session import get_engine
from app.meeting.bot_recall import BotJob, RecallBudgetExceeded, get_bot
from app.meeting.ingest import finalize_meeting

logger = logging.getLogger(__name__)

# Terminal states — refresh_status leaves these alone.
_TERMINAL = {"done", "failed", "cancelled"}

# bot_recall BotJob.status  →  CaptureJob.status
_BOT_TO_CAPTURE = {
    "scheduled": "scheduled",
    "recording": "recording",
    "completed": "transcribing",  # slice 2 ingests, then → done
    "failed": "failed",
}


def platform_from_url(url: str) -> str:
    """meet | zoom | teams | other — from the URL host."""
    host = (urlparse(url).hostname or "").lower()
    if "meet.google" in host:
        return "meet"
    if "zoom" in host:
        return "zoom"
    if "teams.microsoft" in host or "teams.live" in host:
        return "teams"
    return "other"


def _looks_like_meeting_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in {"http", "https"} and bool(p.hostname)


def create_capture_job(
    *,
    tenant_slug: str,
    created_by: str,
    meeting_url: str,
    title: str = "",
    scheduled_start: Optional[datetime] = None,
    duration_minutes: int = 60,
) -> CaptureJob:
    """Schedule a meeting for capture. Raises ValueError on a bad URL, or
    RecallBudgetExceeded if the daily bot budget would be blown."""
    meeting_url = (meeting_url or "").strip()
    if not _looks_like_meeting_url(meeting_url):
        raise ValueError("meeting_url must be an http(s) meeting link")

    job = CaptureJob(
        job_id=f"cap_{uuid.uuid4().hex[:16]}",
        tenant_slug=tenant_slug,
        created_by=created_by,
        meeting_url=meeting_url,
        platform=platform_from_url(meeting_url),
        title=(title or "").strip()[:256],
        scheduled_start=scheduled_start,
        status="queued",
    )

    # Hand the meeting to the bot. get_bot() picks the backend from config
    # (mock by default). A budget breach is surfaced honestly as a failed job,
    # not swallowed.
    bot = get_bot()
    try:
        bot_job = bot.schedule(
            meeting_url=meeting_url,
            tenant_id=tenant_slug,
            duration_minutes=duration_minutes,
            metadata={"capture_job": job.job_id, "title": job.title},
        )
    except RecallBudgetExceeded as exc:
        job.status = "failed"
        job.error_message = f"budget: {exc}"[:512]
        job.bot_backend = bot.backend
        _persist(job)
        logger.warning("capture_budget_exceeded job=%s err=%s", job.job_id, exc)
        return job

    job.bot_id = bot_job.bot_id
    job.bot_backend = bot.backend
    job.estimated_cost_usd = bot_job.estimated_cost_usd
    # The bot's own first status word (mock/recall both start "scheduled").
    job.status = _BOT_TO_CAPTURE.get(bot_job.status, "scheduled")
    _persist(job)
    logger.info(
        "capture_scheduled job=%s backend=%s bot=%s platform=%s",
        job.job_id,
        bot.backend,
        job.bot_id,
        job.platform,
    )
    return job


def list_capture_jobs(tenant_slug: str, limit: int = 100) -> list[CaptureJob]:
    with Session(get_engine()) as db:
        rows = db.exec(
            select(CaptureJob)
            .where(CaptureJob.tenant_slug == tenant_slug)
            .order_by(CaptureJob.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        ).all()
    return list(rows)


def get_capture_job(job_id: str) -> Optional[CaptureJob]:
    with Session(get_engine()) as db:
        return db.exec(select(CaptureJob).where(CaptureJob.job_id == job_id)).first()


def cancel_capture_job(job_id: str) -> Optional[CaptureJob]:
    job = get_capture_job(job_id)
    if job is None:
        return None
    if job.status in _TERMINAL:
        return job
    if job.bot_id:
        try:
            get_bot().cancel(job.bot_id)
        except Exception as exc:  # noqa: BLE001 — cancel is best-effort
            logger.warning("capture_cancel_bot_failed job=%s err=%s", job_id, exc)
    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    _persist(job)
    return job


def refresh_status(job: CaptureJob) -> CaptureJob:
    """Poll the bot backend and map its real status onto the job. Terminal
    jobs, and jobs with no bot (a failed schedule), are returned unchanged.

    When the bot reports the recording is `completed`, the transcript it left
    behind is fed through the same finalize→Meeting→RAG pipeline an upload uses,
    and the job lands on `done` with a `meeting_id`. If the recording is done
    but no transcript has been written yet — or ingestion fails — the job stays
    on `transcribing`, which is honest (recorded, not yet a Meeting) rather than
    a premature `done`."""
    if job.status in _TERMINAL or not job.bot_id:
        return job
    try:
        bot_job = get_bot().status(job.bot_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("capture_status_poll_failed job=%s err=%s", job.job_id, exc)
        return job

    if bot_job.status == "completed":
        return _ingest_completed(job, bot_job)

    mapped = _BOT_TO_CAPTURE.get(bot_job.status)
    if mapped and mapped != job.status:
        job.status = mapped
        if mapped in _TERMINAL:
            job.completed_at = datetime.now(timezone.utc)
        _persist(job)
    return job


def _load_transcript(transcript_path: str) -> Optional[Dict[str, Any]]:
    """Read a recorder's transcript file. The side-car writes the same shape
    `app.services.transcribe` returns: {duration_sec, speakers, segments:[{
    speaker_id, start, end, text}], summary}. Returns None if unreadable."""
    try:
        data = json.loads(Path(transcript_path).read_text())
    except (OSError, ValueError) as exc:
        logger.warning("capture_transcript_unreadable path=%s err=%s", transcript_path, exc)
        return None
    if not isinstance(data, dict) or "segments" not in data:
        logger.warning("capture_transcript_malformed path=%s", transcript_path)
        return None
    return data


def _ingest_completed(job: CaptureJob, bot_job: BotJob) -> CaptureJob:
    """Turn a finished recording into a Meeting. Idempotent: a job already
    carrying a meeting_id is left alone; the same transcript ingested twice
    dedups to one Meeting by content hash."""
    if job.meeting_id is not None:  # already ingested on an earlier poll
        job.status = "done"
        _persist(job)
        return job

    transcript_path = bot_job.transcript_path
    if not transcript_path:
        # Recorded, but the transcript is not on disk yet. Honest holding state.
        if job.status != "transcribing":
            job.status = "transcribing"
            _persist(job)
        return job

    result = _load_transcript(transcript_path)
    if result is None:
        job.status = "transcribing"
        job.error_message = "transcript not readable yet"[:512]
        _persist(job)
        return job

    content_sha256 = hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    title = (job.title or "").strip() or f"Live capture — {job.platform}"

    # Dedup: the same recording turned into a Meeting twice would duplicate every
    # passage in the vector store, where copies read as sources agreeing.
    with Session(get_engine()) as db:
        seen = db.exec(
            select(Meeting)
            .where(Meeting.tenant_slug == job.tenant_slug)
            .where(Meeting.audio_sha256 == content_sha256)
            .where(Meeting.status == "done")
        ).first()
        if seen is not None:
            meeting_id = seen.id
        else:
            meeting = Meeting(
                tenant_slug=job.tenant_slug,
                uploader_email=job.created_by or "capture@local",
                filename=title,
                audio_sha256=content_sha256,
                status="pending",
            )
            db.add(meeting)
            db.commit()
            db.refresh(meeting)
            meeting_id = meeting.id

    if seen is None:
        try:
            finalize_meeting(
                meeting_id=meeting_id,
                result=result,
                filename=title,
                uploader_email=job.created_by or "capture@local",
            )
        except Exception as exc:  # noqa: BLE001 — keep the job retryable
            logger.warning("capture_ingest_failed job=%s err=%s", job.job_id, exc)
            job.status = "transcribing"
            job.error_message = f"ingest: {exc}"[:512]
            _persist(job)
            return job

    job.meeting_id = meeting_id
    job.status = "done"
    job.error_message = None
    job.completed_at = datetime.now(timezone.utc)
    _persist(job)
    logger.info("capture_ingested job=%s meeting=%s", job.job_id, meeting_id)
    return job


def _persist(job: CaptureJob) -> None:
    job.updated_at = datetime.now(timezone.utc)
    with Session(get_engine()) as db:
        db.add(job)
        db.commit()
        db.refresh(job)
