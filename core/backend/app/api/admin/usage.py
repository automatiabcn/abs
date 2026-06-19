# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

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
        "cerebras",
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


def _scan_usage_db(*, since: dt.datetime, week_cutoff: dt.datetime) -> dict[str, Any]:
    """Live provider usage from the DB `usage_log` table — the source the
    cascade actually writes to (`app.services.usage_log.append`) and the one
    `quota_monitor` reads. Without this the panel only saw the legacy
    `rag_usage.jsonl` embedding ledger, so real cascade traffic (anthropic,
    groq, cerebras …) never showed up in the provider mix / free-path %.

    Tolerant of a missing table / engine (cold install) — returns zeros.
    """
    out: dict[str, Any] = {
        "provider_mix": {},
        "free": 0,
        "paid": 0,
        "total": 0,
        "daily": {},
    }
    try:
        from sqlmodel import Session, select

        from app.db.models import UsageLog
        from app.db.session import get_engine

        with Session(get_engine()) as db:
            rows = list(
                db.scalars(select(UsageLog).where(UsageLog.ts >= week_cutoff)).all()
            )
    except Exception as exc:  # pragma: no cover - cold install / no table
        logger.debug("usage db scan skipped: %s", exc)
        return out

    for r in rows:
        ts = r.ts
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        provider = (r.provider or "unknown").lower()
        if ts >= since:
            out["provider_mix"][provider] = out["provider_mix"].get(provider, 0) + 1
            out["total"] += 1
            if provider in FREE_PROVIDERS:
                out["free"] += 1
            elif provider in PAID_PROVIDERS:
                out["paid"] += 1
        if provider == "anthropic":
            day = ts.strftime("%Y-%m-%d")
            out["daily"][day] = out["daily"].get(day, 0) + int(r.tokens or 0)
    return out


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
    # 1) Legacy JSONL ledger (RAG embedding / rerank usage). Optional — a
    #    fresh install has none; we still merge the DB below either way.
    if p.exists():
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

    # 2) Live DB usage_log (cascade provider calls) — merged so the panel
    #    reflects real traffic, not just the embedding ledger.
    db = _scan_usage_db(since=cutoff, week_cutoff=week_cutoff)
    for prov, n in db["provider_mix"].items():
        provider_mix[prov] = provider_mix.get(prov, 0) + n
    total_24h += db["total"]
    free_24h += db["free"]
    paid_24h += db["paid"]
    for day, tok in db["daily"].items():
        daily[day] = daily.get(day, 0) + tok

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
    # 3rd-eye audit — with zero calls there is no free-path ratio; emit None so
    # the tile shows "—". The old default of 1.0 rendered a fabricated "100.0 %"
    # free-path metric on every fresh install that had logged no traffic yet.
    free_pct = (
        scan["free_path_count_24h"] / scan["total_calls_24h"]
        if scan["total_calls_24h"] > 0
        else None
    )
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
            "pct_24h": round(free_pct, 4) if free_pct is not None else None,
        },
        "paid_path": {
            "calls_24h": scan["paid_path_count_24h"],
        },
        "total_calls_24h": scan["total_calls_24h"],
        "provider_mix_24h": scan["provider_mix_24h"],
        "daily_trend": scan["daily_trend"],
    }


__all__ = ["router"]
