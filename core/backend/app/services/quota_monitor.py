# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sprint 20 / CJ-009 — Provider quota monitor.

`get_monthly_usage(provider, start, end)` dondurdugu deger:
    (used: int, limit: int)

Veri kaynagi: app/db/models.py UsageLog tablosu (provider, tokens, ts).
Tablo yoksa graceful 0/0 doner — bootstrap'ta UI bos durumu gosterir.

Quota tablosu (Sprint 20 brief'inden):
- anthropic: 1M tokens / month  (Claude Plus dahil paid tier)
- groq: 200K tokens / day
- gemini: 1500 requests / day
- cerebras: 1M tokens / day
- cohere: 1K tokens / month (free trial)
- cloudflare: 10K neurons / day
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Tuple

logger = logging.getLogger(__name__)


def _anthropic_monthly_limit() -> int:
    """S20.8 — env-driven default. Self-host operator can override per-deployment.

    Default 1_000_000 tokens/month is a chat-equivalent estimate for Claude
    Plus subscription; if the operator runs paid-tier workloads through their
    own Anthropic API key they should set ABS_ANTHROPIC_TOKEN_LIMIT to the
    actual quota purchased.
    """
    try:
        return int(os.environ.get("ABS_ANTHROPIC_TOKEN_LIMIT", "1000000"))
    except ValueError:
        return 1_000_000


# Brief 6.3'ten — provider bazli kota tanimlari.
QUOTAS: dict[str, dict] = {
    "anthropic": {
        "tokens_per_month": _anthropic_monthly_limit(),
        "label": "Claude Plus",
    },
    "groq": {
        "tokens_per_day": 200_000,
        "label": "Groq Free",
    },
    "gemini": {
        "requests_per_day": 1500,
        "label": "Gemini Free",
    },
    "cerebras": {
        "tokens_per_day": 1_000_000,
        "label": "Cerebras Free",
    },
    "cohere": {
        "tokens_per_month": 1_000,
        "label": "Cohere Free Trial",
    },
    "cloudflare": {
        "neurons_per_day": 10_000,
        "label": "Cloudflare Workers AI",
    },
}


def _monthly_limit(provider: str) -> int:
    """Provider icin aylik limit. Daily kotalari 30 ile carpip aylik'a normalize et."""
    if provider == "anthropic":
        return _anthropic_monthly_limit()
    cfg = QUOTAS.get(provider, {})
    if "tokens_per_month" in cfg:
        return int(cfg["tokens_per_month"])
    if "tokens_per_day" in cfg:
        return int(cfg["tokens_per_day"]) * 30
    if "requests_per_day" in cfg:
        return int(cfg["requests_per_day"]) * 30
    if "neurons_per_day" in cfg:
        return int(cfg["neurons_per_day"]) * 30
    return 0


async def _query_usage_sum(provider: str, start: datetime, end: datetime) -> int:
    """Phase 4 / Q2.CO1 — read aggregated tokens via UsageLog service.
    Returns 0 silently if the service or table is unavailable so quota_status
    keeps responding even on cold starts."""
    try:
        from app.services.usage_log import monthly_sum

        tokens, _cost = monthly_sum(provider, start, end)
        return tokens
    except Exception as exc:
        logger.debug(
            "usage_log query unavailable for %s: %s", provider, exc
        )
        return 0


async def get_monthly_usage(
    provider: str, start: datetime, end: datetime
) -> Tuple[int, int]:
    """Provider icin (used, limit) cifti. Bilinmeyen provider → (0, 0)."""
    if provider not in QUOTAS:
        return 0, 0
    used = await _query_usage_sum(provider, start, end)
    return used, _monthly_limit(provider)


def current_period() -> Tuple[datetime, datetime]:
    """Su anki ay'in baslangici (UTC) ve simdi."""
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


def threshold_warnings(percent: float, provider_label: str) -> list[str]:
    """Brief'teki 80%/95% threshold mantigi."""
    out: list[str] = []
    if percent >= 0.95:
        out.append(f"{provider_label}_critical_95")
    elif percent >= 0.80:
        out.append(f"{provider_label}_warning_80")
    return out


__all__ = [
    "QUOTAS",
    "get_monthly_usage",
    "current_period",
    "threshold_warnings",
]
