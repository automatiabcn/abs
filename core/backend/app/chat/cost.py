# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Q12 / Brief 3 R5 — per-message USD estimate for chat transparency.

Resolves the provider's pricing table from `app.providers.configs` and
returns a dict the SSE `meta` frame ships back to the client. The
existing aggregate `app.billing.cost_estimator` works on tracker
counters; this helper is the per-call equivalent.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def estimate_call_cost_usd(
    *,
    provider: str | None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    model: str | None = None,
) -> dict[str, Any]:
    """Return ``{"usd": float, "free": bool, "source": "..."}``.

    `free=True` when no pricing row matches OR all matched pricing
    fields are 0 (e.g. local Ollama, mocked cascade). `usd` is rounded
    to 6 decimals — typical chat replies cost <0.001 USD, so cents
    rounding would underflow to 0.
    """
    if not provider:
        return {"usd": 0.0, "free": True, "source": "no-provider"}

    pricing_row = _lookup_pricing(provider, model)
    if not pricing_row:
        return {"usd": 0.0, "free": True, "source": f"{provider}:no-config"}

    in_per_mtok = float(pricing_row.get("pricing_per_mtok_input", 0))
    out_per_mtok = float(pricing_row.get("pricing_per_mtok_output", 0))
    if in_per_mtok == 0 and out_per_mtok == 0:
        return {"usd": 0.0, "free": True, "source": f"{provider}:zero-priced"}

    usd = (tokens_in / 1_000_000.0) * in_per_mtok + (
        tokens_out / 1_000_000.0
    ) * out_per_mtok
    return {
        "usd": round(usd, 6),
        "free": False,
        "source": f"{provider}:{pricing_row.get('alias') or pricing_row.get('id')}",
    }


def _lookup_pricing(provider: str, model: str | None) -> dict | None:
    """First matching row in the provider's `models` list. Falls back to
    the provider's first model when ``model`` is None or unmatched."""
    try:
        from app.providers.configs import load_all
    except Exception as exc:  # pragma: no cover — provider configs missing
        logger.debug("provider configs unavailable: %s", exc)
        return None

    try:
        cfg = load_all()
    except Exception as exc:
        logger.info("provider config load failed: %s", exc)
        return None

    models = (cfg.get(provider) or {}).get("models") or []
    if not models:
        return None
    if model:
        for m in models:
            if (
                m.get("alias") == model
                or m.get("id") == model
                or model in (m.get("aliases") or [])
            ):
                return m
    return models[0]


__all__ = ["estimate_call_cost_usd"]
