# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""MCP tool kullanım sayacı — panel feat-grid + budget için.

016 — `bump(name, tokens_in=N, tokens_out=M)` token aggregation. Geriye uyumlu:
eski `bump(name)` çağrıları (tokens_in=0, tokens_out=0) hâlâ çalışır.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ToolUsage:
    count_total: int = 0
    count_24h: int = 0
    last_called_at: float = 0.0
    recent_calls: List[float] = field(default_factory=list)  # monotonic timestamps
    # 016 — token aggregation
    tokens_in_24h: int = 0
    tokens_out_24h: int = 0


class UsageTracker:
    def __init__(self) -> None:
        self._by_tool: Dict[str, ToolUsage] = defaultdict(ToolUsage)
        self._lock = asyncio.Lock()

    async def bump(
        self,
        tool_name: str,
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        now = time.monotonic()
        async with self._lock:
            u = self._by_tool[tool_name]
            u.count_total += 1
            u.last_called_at = now
            u.recent_calls.append(now)
            day_ago = now - 24 * 3600
            u.recent_calls = [t for t in u.recent_calls if t >= day_ago]
            u.count_24h = len(u.recent_calls)
            u.tokens_in_24h += int(tokens_in or 0)
            u.tokens_out_24h += int(tokens_out or 0)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        return {
            name: {
                "count_total": u.count_total,
                "count_24h": u.count_24h,
                "last_called_at": u.last_called_at,
                "tokens_in_24h": u.tokens_in_24h,
                "tokens_out_24h": u.tokens_out_24h,
            }
            for name, u in self._by_tool.items()
        }


tracker = UsageTracker()
