"""BUG-V1 — `/v1/admin/usage` aggregated tenant usage view.

Powers the `/admin/usage` admin widget (PROMISE.md vow):
  - `claude_budget_pct` — quota_monitor.status() used%
  - `free_path_pct`     — free providers vs paid (anthropic) call share
                          over the last 24h (rag_usage.jsonl is the
                          single-source-of-truth as of T-016 / T-018).
  - `provider_mix_24h`  — per-provider call counts (last 24h).
  - `daily_trend`       — 7-day token series (Claude only) so the UI
                          can chart a sparkline.

The endpoint is read-only and tolerant of missing data (cold install)
— it returns zeroes rather than 5xx so the admin shell stays usable.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
from typing import Any

from fastapi import APIRouter, Depends

from app.api.admin.auth import admin_required
from app.config import settings
from app.observability import quota_monitor

router = APIRouter(prefix="/v1/admin/usage", tags=["admin"])
logger = logging.getLogger(__name__)

# Providers ABS calls "free path" — same set as PROMISE.md table.
FREE_PROVIDERS = frozenset(
    {
        "groq",
        "cloudflare",
        "gemini",
        "cohere",
        "ollama",
        "local",
        "mlx",
        "bge-m3-mock",  # historical fixture name, treated as free
    }
)
PAID_PROVIDERS = frozenset({"anthropic", "openai"})


def _usage_log_path() -> pathlib.Path:
    raw = getattr(settings, "usage_log_path", "data/rag_usage.jsonl")
    return pathlib.Path(raw)


def _model_to_provider(model: str) -> str:
    """Map a model_version string to the canonical provider tag."""
    m = (model or "").lower()
    if "claude" in m or "anthropic" in m:
        return "anthropic"
    if "gpt-oss" in m or "groq" in m or "llama" in m or "kimi" in m or "qwen" in m:
        return "groq"
    if "gemini" in m:
        return "gemini"
    if "cohere" in m or "embed-english" in m or "rerank" in m:
        return "cohere"
    if "cloudflare" in m or "@cf/" in m:
        return "cloudflare"
    if "ollama" in m or "phi-" in m or "gemma-" in m or "codellama" in m:
        return "ollama"
    if "openai" in m or "text-embedding-3" in m:
        return "openai"
    if "bge-m3" in m:
        return "bge-m3-mock"
    return "unknown"


def _scan_usage(
    *,
    path: pathlib.Path | None = None,
    since: dt.datetime | None = None,
) -> dict[str, Any]:
    """Aggregate the JSONL ledger into provider counts + daily series."""
    p = path or _usage_log_path()
    cutoff = since or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24))
    cutoff_iso = cutoff.isoformat(timespec="seconds")
    week_cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
    provider_mix: dict[str, int] = {}
    daily: dict[str, int] = {}  # YYYY-MM-DD -> claude tokens
    total_24h = 0
    free_24h = 0
    paid_24h = 0
    if not p.exists():
        # Cold install: still return the dense 7-day trend (zeros) so
        # the chart container has slots to render.
        today = dt.datetime.now(dt.timezone.utc).date()
        empty_trend = [
            {
                "day": (today - dt.timedelta(days=offset)).isoformat(),
                "claude_tokens": 0,
            }
            for offset in range(6, -1, -1)
        ]
        return {
            "provider_mix_24h": provider_mix,
            "daily_trend": empty_trend,
            "free_path_count_24h": free_24h,
            "paid_path_count_24h": paid_24h,
            "total_calls_24h": total_24h,
        }
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(row.get("timestamp") or "")
            provider = _model_to_provider(str(row.get("model_version") or ""))
            # 24h provider mix
            if ts and ts >= cutoff_iso:
                provider_mix[provider] = provider_mix.get(provider, 0) + 1
                total_24h += 1
                if provider in FREE_PROVIDERS:
                    free_24h += 1
                elif provider in PAID_PROVIDERS:
                    paid_24h += 1
            # 7-day claude token series for the chart
            if ts and provider == "anthropic":
                try:
                    parsed = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if parsed >= week_cutoff:
                    day = parsed.strftime("%Y-%m-%d")
                    tokens = int(row.get("input_tokens", 0)) + int(
                        row.get("output_tokens", 0)
                    )
                    daily[day] = daily.get(day, 0) + tokens
    # Build dense 7-day series so the chart has a slot per day even when 0.
    today = dt.datetime.now(dt.timezone.utc).date()
    trend = [
        {
            "day": (today - dt.timedelta(days=offset)).isoformat(),
            "claude_tokens": daily.get(
                (today - dt.timedelta(days=offset)).isoformat(), 0
            ),
        }
        for offset in range(6, -1, -1)
    ]
    return {
        "provider_mix_24h": provider_mix,
        "daily_trend": trend,
        "free_path_count_24h": free_24h,
        "paid_path_count_24h": paid_24h,
        "total_calls_24h": total_24h,
    }


@router.get("")
async def get_usage(_admin: dict = Depends(admin_required)) -> dict[str, Any]:
    """Return the aggregated usage payload for the admin widget.

    The shape is locked by the Playwright + pytest contract — extend
    additively (don't rename).
    """
    quota = quota_monitor.status()
    scan = _scan_usage()
    free_pct = 1.0
    if scan["total_calls_24h"] > 0:
        free_pct = scan["free_path_count_24h"] / scan["total_calls_24h"]
    return {
        "month": quota.month,
        "claude": {
            "limit_tokens": quota.limit_tokens,
            "used_tokens": quota.used_tokens,
            "used_pct": round(quota.used_pct, 4),
            "over_warn": quota.over_warn,
            "over_block": quota.over_block,
            "banner": quota.banner(),
        },
        "free_path": {
            "calls_24h": scan["free_path_count_24h"],
            "pct_24h": round(free_pct, 4),
        },
        "paid_path": {
            "calls_24h": scan["paid_path_count_24h"],
        },
        "total_calls_24h": scan["total_calls_24h"],
        "provider_mix_24h": scan["provider_mix_24h"],
        "daily_trend": scan["daily_trend"],
    }


__all__ = ["router"]
