# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""014 — Provider health monitor (60s background loop).

Her interval'da registered provider'lara cheap ping atar. SSE
`_build_orchestrator` event'i bu monitor'in snapshot'ini gosterir
(random placeholder yerine).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.config import settings
from app.providers.registry import get_registry
from app.providers.schemas import ProviderError

logger = logging.getLogger(__name__)


_PING_PROMPT = "ok"
_PING_MAX_TOKENS = 5


@dataclass
class ProviderHealth:
    provider: str
    state: str = "unknown"  # ok | warn | down | unknown
    latency_ms: int = 0
    last_check_at: float = 0.0
    last_error: Optional[str] = None
    consecutive_failures: int = 0


_KEY_MAP = {
    "groq": "groq_api_key",
    "cerebras": "cerebras_api_key",
    "gemini": "gemini_api_key",
    "cloudflare": "cf_api_token",
    "anthropic": "anthropic_api_key",
    "ollama": "ollama_url",
    "mlx": "mlx_url",
}


def _provider_has_credentials(name: str) -> bool:
    attr = _KEY_MAP.get(name)
    if not attr:
        return False
    return bool(getattr(settings, attr, ""))


class HealthMonitor:
    def __init__(self, interval_seconds: Optional[int] = None) -> None:
        self.interval = interval_seconds or settings.health_interval_seconds
        self._results: Dict[str, ProviderHealth] = {}
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def snapshot(self) -> List[Dict]:
        return [
            {
                "name": h.provider.title(),
                "state": h.state,
                "latency_ms": h.latency_ms,
                "last_check_at": h.last_check_at,
                "last_error": h.last_error,
            }
            for h in sorted(self._results.values(), key=lambda x: x.provider)
        ]

    async def _ping_one(self, provider_name: str) -> ProviderHealth:
        h = self._results.setdefault(
            provider_name, ProviderHealth(provider=provider_name)
        )
        h.last_check_at = time.time()
        if not _provider_has_credentials(provider_name):
            h.state = "unknown"
            h.last_error = "no credentials configured"
            return h
        provider = get_registry()[provider_name]
        start = time.monotonic()
        try:
            await provider.call(_PING_PROMPT, max_tokens=_PING_MAX_TOKENS, timeout=8.0)
            h.latency_ms = int((time.monotonic() - start) * 1000)
            h.state = "ok" if h.latency_ms < 3000 else "warn"
            h.last_error = None
            h.consecutive_failures = 0
        except (ProviderError, Exception) as exc:
            h.latency_ms = int((time.monotonic() - start) * 1000)
            h.consecutive_failures += 1
            h.last_error = str(exc)[:200]
            h.state = "down" if h.consecutive_failures >= 2 else "warn"
        return h

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            registry = get_registry()
            tasks = [self._ping_one(n) for n in registry.keys()]
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as exc:
                logger.warning("health monitor cycle fail: %s", exc)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.interval
                )
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()


monitor = HealthMonitor()
