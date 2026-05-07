# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-F01 — Manual audio upload pipeline.

Accept .mp3/.mp4/.wav from a tenant, persist to the local recordings dir,
hand off to the existing `Transcriber` (whisperx local or mock in tests),
and emit a `BotJob`-compatible record so downstream nodes (T-S03 workflow
node `abs.meeting_transcribe`) keep their interface.
"""

from __future__ import annotations

import logging
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Iterable

from app.config import settings

from .bot_local import LocalMeetingBackend, transition
from .bot_recall import BotJob
from .transcribe import Transcript, get_transcriber

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS: tuple[str, ...] = (".mp3", ".mp4", ".wav", ".m4a", ".webm")


class UploadError(RuntimeError):
    """Raised when an uploaded file fails validation."""


def _recordings_dir() -> pathlib.Path:
    base = pathlib.Path(
        getattr(settings, "meeting_recordings_dir", "/tmp/abs-meetings/recordings")
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


def _validate_extension(filename: str, allowed: Iterable[str] = ALLOWED_EXTENSIONS) -> str:
    ext = pathlib.Path(filename).suffix.lower()
    if ext not in allowed:
        raise UploadError(f"unsupported audio extension: {ext!r}")
    return ext


def accept_upload(
    *,
    tenant_id: str,
    filename: str,
    payload: bytes,
    metadata: dict[str, str] | None = None,
    jobs_dir: pathlib.Path | None = None,
) -> tuple[BotJob, Transcript]:
    """Persist payload, transcribe via the configured Transcriber, return both."""
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise UploadError("tenant_id must be a non-empty string")
    _validate_extension(filename)
    if not payload:
        raise UploadError("upload payload is empty")

    bot_id = uuid.uuid4().hex[:12]
    safe_name = f"{tenant_id}__{bot_id}__{pathlib.Path(filename).name}"
    target = _recordings_dir() / safe_name
    target.write_bytes(payload)

    backend = LocalMeetingBackend(jobs_dir=jobs_dir)
    job = backend.schedule(
        meeting_url=f"file://{target}",
        tenant_id=tenant_id,
        metadata=dict(metadata or {}, source="upload_manual", file=safe_name),
    )

    transcript = get_transcriber().transcribe(target)
    transcript_path = target.with_suffix(".transcript.txt")
    transcript_path.write_text(transcript.text(), encoding="utf-8")
    transition(
        job.bot_id,
        status="completed",
        transcript_path=str(transcript_path),
        jobs_dir=backend._dir,
    )
    logger.info(
        "meeting_upload tenant=%s bot=%s file=%s segs=%d",
        tenant_id,
        job.bot_id,
        safe_name,
        len(transcript.segments),
    )
    final = backend.status(job.bot_id)
    return final, transcript


def wer(reference: str, hypothesis: str) -> float:
    """Levenshtein-based Word Error Rate (used by tests + runbooks)."""
    ref = reference.split()
    hyp = hypothesis.split()
    if not ref:
        return 0.0 if not hyp else 1.0
    n, m = len(ref), len(hyp)
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[m] / float(n)


def google_calendar_pickup_stub(events: list[dict]) -> list[dict]:
    """Cron-based pickup hook for Google Calendar events.

    Real implementation will call the Calendar API; here we return the events
    annotated with a runner manifest so the runbook + tests can exercise the
    flow without a network round-trip.
    """
    out: list[dict] = []
    backend = LocalMeetingBackend()
    for ev in events:
        url = ev.get("hangoutLink") or ev.get("location") or ""
        tenant = ev.get("tenant_id") or ev.get("organizer", {}).get("email", "unknown")
        if not url:
            continue
        job = backend.schedule(
            meeting_url=url,
            tenant_id=tenant,
            metadata={
                "calendar_event_id": ev.get("id", ""),
                "summary": ev.get("summary", "")[:120],
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        )
        out.append(
            {
                "calendar_event_id": ev.get("id"),
                "bot_id": job.bot_id,
                "meeting_url": url,
            }
        )
    return out


__all__ = [
    "ALLOWED_EXTENSIONS",
    "UploadError",
    "accept_upload",
    "google_calendar_pickup_stub",
    "wer",
]
