# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-026 — Recall.ai meeting bot wrapper (calendar event → bot → audio).

Mock backend simulates the bot lifecycle with deterministic state transitions
so tests don't need a Recall.ai account. Real backend gated behind deferred
import + cost guard (`recall_ai_cost_cap_usd_per_day`).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "BotJob",
    "RecallBudgetExceeded",
    "MeetingBot",
    "close_bot",
    "get_bot",
]


class RecallBudgetExceeded(RuntimeError):
    """Raised when scheduling the bot would exceed the daily budget."""


@dataclass(slots=True)
class BotJob:
    bot_id: str
    meeting_url: str
    tenant_id: str
    scheduled_at: str
    status: str = "scheduled"  # scheduled | recording | completed | failed
    transcript_path: str | None = None
    estimated_cost_usd: float = 0.0
    metadata: dict[str, str] = field(default_factory=dict)


class _MockBackend:
    def __init__(self) -> None:
        self._jobs: dict[str, BotJob] = {}
        logger.info("recall_mock_init")

    def schedule(
        self,
        *,
        meeting_url: str,
        tenant_id: str,
        cost_estimate_usd: float,
        metadata: dict[str, str] | None = None,
    ) -> BotJob:
        job = BotJob(
            bot_id=uuid.uuid4().hex[:12],
            meeting_url=meeting_url,
            tenant_id=tenant_id,
            scheduled_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            estimated_cost_usd=cost_estimate_usd,
            metadata=dict(metadata or {}),
        )
        self._jobs[job.bot_id] = job
        return job

    def status(self, bot_id: str) -> BotJob:
        job = self._jobs.get(bot_id)
        if job is None:
            raise KeyError(f"bot_id {bot_id!r} not found")
        return job

    def cancel(self, bot_id: str) -> None:
        self._jobs.pop(bot_id, None)


class _RecallBackend:
    """T-Q03 — real Recall.ai client using httpx.

    Endpoints (per https://docs.recall.ai/reference):
      POST   /api/v1/bot           schedule a new bot
      GET    /api/v1/bot/<id>      query bot status
      DELETE /api/v1/bot/<id>      cancel a scheduled bot

    Auth: `Authorization: Token <api_key>` header.
    """

    BASE_URL = "https://api.recall.ai"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("recall_ai_api_key not set")
        try:
            import httpx  # noqa: F401
        except ImportError as exc:
            raise ImportError("recall backend requires httpx") from exc
        self.api_key = api_key
        logger.info("recall_live_init")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

    def schedule(
        self,
        *,
        meeting_url: str,
        tenant_id: str,
        cost_estimate_usd: float,
        metadata: dict[str, str] | None = None,
        **_: Any,
    ) -> BotJob:
        import httpx

        payload: dict[str, Any] = {
            "meeting_url": meeting_url,
            "bot_name": f"abs-{tenant_id[:8]}",
            "metadata": dict(metadata or {}, abs_tenant=tenant_id),
        }
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{self.BASE_URL}/api/v1/bot",
                json=payload,
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
        return BotJob(
            bot_id=str(data["id"]),
            meeting_url=meeting_url,
            tenant_id=tenant_id,
            scheduled_at=data.get("created_at")
            or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            status=str(data.get("status", "scheduled")),
            estimated_cost_usd=cost_estimate_usd,
            metadata=dict(metadata or {}),
        )

    def status(self, bot_id: str) -> BotJob:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            r = client.get(
                f"{self.BASE_URL}/api/v1/bot/{bot_id}",
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
        return BotJob(
            bot_id=str(data["id"]),
            meeting_url=str(data.get("meeting_url", "")),
            tenant_id=str(data.get("metadata", {}).get("abs_tenant", "")),
            scheduled_at=str(data.get("created_at", "")),
            status=str(data.get("status", "unknown")),
            transcript_path=data.get("transcript_url"),
            metadata=dict(data.get("metadata", {})),
        )

    def cancel(self, bot_id: str) -> None:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            r = client.delete(
                f"{self.BASE_URL}/api/v1/bot/{bot_id}",
                headers=self._headers(),
            )
            r.raise_for_status()


class MeetingBot:
    backend: str

    def __init__(self, backend_name: str | None = None) -> None:
        backend = backend_name or getattr(settings, "recall_backend", "mock") or "mock"
        self.backend = backend
        if backend == "mock":
            self._impl: Any = _MockBackend()
        elif backend == "local":
            # T-F01 — self-hosted meetily/jitsi backend (free tier default).
            from .bot_local import LocalMeetingBackend

            self._impl = LocalMeetingBackend()
        elif backend == "recall":
            # T-F01 — Recall.ai is now opt-in. Require explicit env flag.
            recall_enabled = bool(getattr(settings, "recall_enabled", False))
            if not recall_enabled:
                raise ValueError(
                    "Recall.ai backend is opt-in; set ABS_RECALL_ENABLED=true to use it"
                )
            self._impl = _RecallBackend(
                api_key=getattr(settings, "recall_ai_api_key", "") or "",
            )
        else:
            raise ValueError(f"unsupported recall backend: {backend}")
        self._spent_today_usd = 0.0
        self._spent_window_start = time.time()

    def _budget_check(self, cost: float) -> None:
        cap = float(getattr(settings, "recall_ai_cost_cap_usd_per_day", 50.0))
        # Reset rolling 24h window.
        if time.time() - self._spent_window_start > 86400:
            self._spent_today_usd = 0.0
            self._spent_window_start = time.time()
        if self._spent_today_usd + cost > cap:
            raise RecallBudgetExceeded(
                f"daily cap ${cap:.2f} would be breached "
                f"(spent ${self._spent_today_usd:.2f} + new ${cost:.2f})"
            )

    def schedule(
        self,
        *,
        meeting_url: str,
        tenant_id: str,
        duration_minutes: int = 60,
        metadata: dict[str, str] | None = None,
    ) -> BotJob:
        cost = (duration_minutes / 60.0) * 0.50  # brief: $0.50/recording-hour
        self._budget_check(cost)
        job = self._impl.schedule(
            meeting_url=meeting_url,
            tenant_id=tenant_id,
            cost_estimate_usd=cost,
            metadata=metadata,
        )
        self._spent_today_usd += cost
        logger.info(
            "recall_schedule tenant=%s bot=%s duration=%dm cost=$%.2f",
            tenant_id,
            job.bot_id,
            duration_minutes,
            cost,
        )
        return job

    def status(self, bot_id: str) -> BotJob:
        return self._impl.status(bot_id)

    def cancel(self, bot_id: str) -> None:
        self._impl.cancel(bot_id)

    def close(self) -> None:
        return None


_singleton: MeetingBot | None = None


def get_bot() -> MeetingBot:
    global _singleton
    if _singleton is None:
        _singleton = MeetingBot()
    return _singleton


def close_bot() -> None:
    global _singleton
    if _singleton is None:
        return
    try:
        _singleton.close()
    finally:
        _singleton = None
