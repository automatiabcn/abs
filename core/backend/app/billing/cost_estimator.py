"""015 — Tracker × provider_configs pricing → günlük tahmini maliyet.

Token sayisi tracker'da tutulmuyor (sadece count_24h). Ortalama 1500 tok/call,
30/70 input/output split varsayimi. Gercek token tracking 016+'da.
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
    """`ask_<alias>` veya `ask_<id-normalized>` → (provider, alias, model_dict).

    Provider configs YAML'larından dynamic build.
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
        # 016 — gercek token sayisi varsa kullan, yoksa eski avg fallback
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
        "Gercek token tracking aktif (016)."
        if has_real_tokens
        else "Token sayisi tahmini (1500 avg, 30/70 split). Gercek tracking icin pipeline tool'lari token forward etmeli."
    )
    return {
        "today_usd": round(total_usd, 2),
        "projected_monthly_usd": round(total_usd * 30, 2),
        "by_provider": by_provider,
        "breakdown": sorted(breakdown, key=lambda x: -x["estimated_usd"])[:10],
        "estimated_at": time.time(),
        "note": note,
    }
