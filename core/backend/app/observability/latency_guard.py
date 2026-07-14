# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sliding-window p95 latency guard.

Tracks the most recent N samples per route and emits a structured `Alert`
record when p95 breaches the configured budget. Used to wire LangFuse
alerts + the Slack/Telegram notification hook.
"""

from __future__ import annotations

import collections
import logging
import math
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = [
    "LatencyAlert",
    "LatencyGuard",
]


@dataclass(slots=True)
class LatencyAlert:
    route: str
    p95_ms: float
    budget_ms: float
    sample_size: int


class LatencyGuard:
    def __init__(self, *, budget_ms: float = 3000.0, window: int = 200) -> None:
        if budget_ms <= 0:
            raise ValueError("budget_ms must be > 0")
        if window <= 0:
            raise ValueError("window must be > 0")
        self.budget_ms = budget_ms
        self.window = window
        self._buckets: dict[str, collections.deque[float]] = {}

    def record(self, *, route: str, latency_ms: float) -> LatencyAlert | None:
        if not route:
            raise ValueError("route required")
        bucket = self._buckets.setdefault(route, collections.deque(maxlen=self.window))
        bucket.append(float(latency_ms))
        if len(bucket) < max(20, self.window // 4):
            return None
        ordered = sorted(bucket)
        idx = max(0, math.ceil(0.95 * len(ordered)) - 1)
        p95 = ordered[idx]
        if p95 > self.budget_ms:
            alert = LatencyAlert(
                route=route,
                p95_ms=p95,
                budget_ms=self.budget_ms,
                sample_size=len(bucket),
            )
            logger.warning(
                "latency_alert route=%s p95=%.1fms budget=%.1fms",
                route,
                p95,
                self.budget_ms,
            )
            return alert
        return None

    def snapshot(self, route: str) -> dict[str, float | int]:
        bucket = self._buckets.get(route)
        if not bucket:
            return {"sample_size": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
        ordered = sorted(bucket)
        n = len(ordered)
        return {
            "sample_size": n,
            "p50_ms": ordered[max(0, n // 2 - 1)],
            "p95_ms": ordered[max(0, math.ceil(0.95 * n) - 1)],
            "p99_ms": ordered[max(0, math.ceil(0.99 * n) - 1)],
        }
