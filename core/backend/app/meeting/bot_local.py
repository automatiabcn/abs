"""T-F01 — Self-hosted meeting bot backend (meetily / jitsi).

Free-tier replacement for `bot_recall._RecallBackend`. The Python side just
writes a job manifest under `meeting_local_jobs_dir`; an external meetily or
jitsi side-car picks it up, records the meeting, and calls `transition()` to
mark the job complete with a transcript path. Unit tests do not shell out.
"""

from __future__ import annotations

import json
import logging
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import settings

from .bot_recall import BotJob

logger = logging.getLogger(__name__)

SUPPORTED_RUNNERS = ("meetily", "jitsi")


class LocalRunnerError(RuntimeError):
    """Raised when the local runner configuration is invalid."""


def _runner() -> str:
    runner = (getattr(settings, "meeting_local_runner", "meetily") or "meetily").lower()
    if runner not in SUPPORTED_RUNNERS:
        raise LocalRunnerError(f"unsupported local runner: {runner!r}")
    return runner


def _jobs_dir() -> pathlib.Path:
    base = pathlib.Path(getattr(settings, "meeting_local_jobs_dir", "/tmp/abs-meetings"))
    base.mkdir(parents=True, exist_ok=True)
    return base


class LocalMeetingBackend:
    """Job-manifest-based meeting bot backend."""

    def __init__(self, *, jobs_dir: pathlib.Path | None = None) -> None:
        self._dir = pathlib.Path(jobs_dir) if jobs_dir is not None else _jobs_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._runner = _runner()
        logger.info("meeting_local_init runner=%s dir=%s", self._runner, self._dir)

    def _manifest_path(self, bot_id: str) -> pathlib.Path:
        return self._dir / f"{bot_id}.json"

    def schedule(
        self,
        *,
        meeting_url: str,
        tenant_id: str,
        cost_estimate_usd: float = 0.0,
        metadata: dict[str, str] | None = None,
    ) -> BotJob:
        bot_id = uuid.uuid4().hex[:12]
        job = BotJob(
            bot_id=bot_id,
            meeting_url=meeting_url,
            tenant_id=tenant_id,
            scheduled_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            estimated_cost_usd=0.0,  # self-host: $0
            metadata=dict(metadata or {}, runner=self._runner),
        )
        manifest = {
            "bot_id": job.bot_id,
            "meeting_url": meeting_url,
            "tenant_id": tenant_id,
            "scheduled_at": job.scheduled_at,
            "status": "scheduled",
            "runner": self._runner,
            "metadata": job.metadata,
        }
        self._manifest_path(bot_id).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False)
        )
        logger.info(
            "meeting_local_schedule tenant=%s bot=%s url=%s",
            tenant_id,
            bot_id,
            meeting_url,
        )
        return job

    def status(self, bot_id: str) -> BotJob:
        path = self._manifest_path(bot_id)
        if not path.exists():
            raise KeyError(f"bot_id {bot_id!r} not found")
        data: dict[str, Any] = json.loads(path.read_text())
        return BotJob(
            bot_id=str(data["bot_id"]),
            meeting_url=str(data["meeting_url"]),
            tenant_id=str(data["tenant_id"]),
            scheduled_at=str(data["scheduled_at"]),
            status=str(data.get("status", "scheduled")),
            transcript_path=data.get("transcript_path"),
            estimated_cost_usd=0.0,
            metadata=dict(data.get("metadata", {})),
        )

    def cancel(self, bot_id: str) -> None:
        path = self._manifest_path(bot_id)
        if path.exists():
            path.unlink()


def transition(
    bot_id: str,
    *,
    status: str,
    transcript_path: str | None = None,
    jobs_dir: pathlib.Path | None = None,
) -> BotJob:
    """Update a manifest's status (used by the runner side-car or tests)."""
    backend = LocalMeetingBackend(jobs_dir=jobs_dir)
    p = backend._manifest_path(bot_id)
    if not p.exists():
        raise KeyError(f"bot_id {bot_id!r} not found")
    data: dict[str, Any] = json.loads(p.read_text())
    data["status"] = status
    if transcript_path is not None:
        data["transcript_path"] = transcript_path
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return backend.status(bot_id)


__all__ = [
    "LocalMeetingBackend",
    "LocalRunnerError",
    "SUPPORTED_RUNNERS",
    "transition",
]
