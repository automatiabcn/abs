# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Estimated daily spend — call tracker × provider_configs pricing.

The tracker records call counts, not token counts, so the estimate assumes an
average of 1500 tokens per call with a 30/70 input/output split. It is an
order-of-magnitude figure, not an invoice.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.mcp.tracking import tracker
from app.providers.configs import load_all

logger = logging.getLogger(__name__)


_AVG_TOKENS_PER_CALL = 1500
_INPUT_RATIO = 0.3
_OUTPUT_RATIO = 0.7


def _build_alias_index() -> Dict[str, tuple]:
    """Index `ask_<alias>` and `ask_<id-normalized>` → (provider, alias, model).

    Built from the provider config YAMLs, so a newly added model is priced
    without touching this module.
    """
    cfg = load_all()
    index: Dict[str, tuple] = {}
    for provider, data in cfg.items():
        for m in data.get("models") or []:
            alias = m.get("alias", "")
            mid = (m.get("id") or "").replace("-", "_").replace("/", "_").lower()
            for candidate in (
                f"ask_{alias}",
                f"ask_{mid}",
            ):
                if candidate and candidate not in index:
                    index[candidate] = (provider, alias, m)
    return index


def _model_to_provider(tool_name: str) -> Optional[tuple]:
    return _build_alias_index().get(tool_name)


def estimate_daily_cost() -> Dict[str, Any]:
    """tracker.snapshot() × provider_configs pricing → today_usd + breakdown."""
    snap = tracker.snapshot()
    total_usd = 0.0
    by_provider: Dict[str, float] = {}
    breakdown: List[Dict[str, Any]] = []
    index = _build_alias_index()

    has_real_tokens = False
    for tool_name, usage in snap.items():
        match = index.get(tool_name)
        if not match:
            continue
        provider, alias, model = match
        calls = int(usage.get("count_24h", 0))
        if not calls:
            continue
        # Real token counts when the tracker has them, the average otherwise.
        tok_in_real = int(usage.get("tokens_in_24h", 0) or 0)
        tok_out_real = int(usage.get("tokens_out_24h", 0) or 0)
        exact = tok_in_real > 0 or tok_out_real > 0
        if exact:
            in_tok = tok_in_real
            out_tok = tok_out_real
            has_real_tokens = True
        else:
            in_tok = int(calls * _AVG_TOKENS_PER_CALL * _INPUT_RATIO)
            out_tok = int(calls * _AVG_TOKENS_PER_CALL * _OUTPUT_RATIO)
        cost_in = (in_tok / 1_000_000) * float(model.get("pricing_per_mtok_input", 0))
        cost_out = (out_tok / 1_000_000) * float(model.get("pricing_per_mtok_output", 0))
        cost = round(cost_in + cost_out, 4)
        total_usd += cost
        by_provider[provider] = round(by_provider.get(provider, 0.0) + cost, 4)
        breakdown.append(
            {
                "tool": tool_name,
                "provider": provider,
                "model_alias": alias,
                "calls_24h": calls,
                "tokens_in": in_tok,
                "tokens_out": out_tok,
                "exact": exact,
                "estimated_usd": cost,
            }
        )

    note = (
        "Real token tracking is active."
        if has_real_tokens
        else "Token counts are estimated (1500 avg, 30/70 split). For exact figures the pipeline tools must forward token usage."
    )
    return {
        "today_usd": round(total_usd, 2),
        "projected_monthly_usd": round(total_usd * 30, 2),
        "by_provider": by_provider,
        "breakdown": sorted(breakdown, key=lambda x: -x["estimated_usd"])[:10],
        "estimated_at": time.time(),
        "note": note,
    }
