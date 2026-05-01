"""Judge log + stats MCP tool'ları (009)."""

from __future__ import annotations

import json
from typing import List

from app.judge.log import read_recent, update_outcome
from app.judge.stats import aggregate
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("judge_stats")
async def judge_stats(window_days: int = 7) -> str:
    """Son N günün judgment ortalamaları + drift_signal + outcome_counts + top_files."""
    await tracker.bump("judge_stats")
    return json.dumps(aggregate(window_days=window_days), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("judge_recent")
async def judge_recent(limit: int = 20) -> str:
    """Son N judgment kaydı (id, ts, file, ast/llm/combined, outcome)."""
    await tracker.bump("judge_recent")
    return json.dumps(read_recent(limit=limit), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("judge_outcome")
async def judge_outcome(judgment_id: str, outcome: str = "accept") -> str:
    """Bir judgment'a outcome işaretle (accept|reject)."""
    await tracker.bump("judge_outcome")
    ok = update_outcome(judgment_id, outcome)
    return json.dumps({"ok": ok, "judgment_id": judgment_id, "outcome": outcome})


REGISTERED_TOOLS.extend(["judge_stats", "judge_recent", "judge_outcome"])
