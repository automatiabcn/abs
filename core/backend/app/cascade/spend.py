# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""A ceiling on what a paid provider may spend in a day.

**Dormant on purpose — nothing calls this yet.** The founder's ruling (08-02):
a spend cap is as dangerous as no cap when the arithmetic is wrong, because a
wrong number refuses work that was affordable and does it invisibly. So the
ledger is written and tested, and the cascade does not consult it. `cap_usd()`
is 0 by default, which is off. Wiring it in is a deliberate later decision, and
it needs real prices behind it first — see `is_priced`.

The pivot document names opaque cost as the wound this product is built
against, and promises the opposite: your own key, a visible rate, **a hard
cap**, and a cost you can see before the call. Audited 2026-08-02: the cap did
not exist. The quota meter counts requests and tokens; nothing counted money, and nothing stopped it. A
developer who pasted an Anthropic key had no ceiling at all.

Three rules, and the second is the one that makes the other two worth having:

* **Free providers are never blocked.** ABS routes to free tiers first and a
  free call cannot spend anything; refusing one to protect a budget would be
  theatre.
* **Unknown pricing is not zero.** `estimate_cost_usd` returns 0.0 when a model
  is missing from the table — which is exactly how an unpriced paid model would
  slip past a cap that trusted it. A paid provider we cannot price is reported
  as unknown and refused when the cap is on, because "we could not work out
  what this costs" is a reason to stop, not to proceed.
* **A refusal says when it lifts.** The ceiling is daily and resets at UTC
  midnight, so the message is the same shape as a spent quota: not "you are
  out", but "you are out until then".
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional, Tuple

from app.observability.cost_table import estimate_cost_usd, lookup

_lock = threading.Lock()
_state: dict[str, dict] = {}

# What a call is assumed to weigh when nobody said. Deliberately generous: a
# guess that is too small is a cap that does not hold.
ASSUMED_INPUT_TOKENS = 4000
ASSUMED_OUTPUT_TOKENS = 1000


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _key(tenant_id: Optional[str]) -> str:
    return tenant_id or "default"


def _get(tenant_id: Optional[str]) -> dict:
    """The day's ledger, rolled over at UTC midnight."""
    k = _key(tenant_id)
    today = _utc_today()
    cur = _state.get(k)
    if cur is None or cur.get("day") != today:
        cur = {"day": today, "usd": 0.0, "calls": 0, "unpriced_calls": 0}
        _state[k] = cur
    return cur


def cap_usd() -> float:
    """The ceiling. Zero or less means no ceiling — and that is a choice, not
    a default, so it has to be set deliberately."""
    try:
        from app.config import settings

        return float(getattr(settings, "daily_spend_cap_usd", 0.0) or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def spent_today(tenant_id: Optional[str] = "default") -> float:
    with _lock:
        return round(float(_get(tenant_id)["usd"]), 6)


def is_priced(provider: str, model: str) -> bool:
    """Do we know what this costs? Missing from the table is not free."""
    return lookup(provider, model) is not None


def record(
    *,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    tenant_id: Optional[str] = "default",
    free: bool = False,
) -> float:
    """Add one call to the day's ledger. Returns what it added. Never raises."""
    if free:
        return 0.0
    try:
        usd = estimate_cost_usd(
            provider=provider,
            model=model,
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
        )
    except Exception:  # noqa: BLE001 — a ledger must not break a working call
        usd = 0.0
    with _lock:
        day = _get(tenant_id)
        day["usd"] = float(day["usd"]) + float(usd)
        day["calls"] = int(day["calls"]) + 1
        if not is_priced(provider, model):
            # Counted separately so the readout can admit the total is a floor
            # rather than presenting a number it cannot stand behind.
            day["unpriced_calls"] = int(day["unpriced_calls"]) + 1
    return float(usd)


def minutes_to_reset(now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    return int(((24 - now.hour) * 60) - now.minute) % (24 * 60) or 24 * 60


def would_exceed(
    *,
    provider: str,
    model: str,
    tenant_id: Optional[str] = "default",
    free: bool = False,
    input_tokens: int = ASSUMED_INPUT_TOKENS,
    output_tokens: int = ASSUMED_OUTPUT_TOKENS,
) -> Tuple[bool, str]:
    """May this call go ahead? Returns (blocked, reason).

    The reason is written for the person who will read it in the panel, and it
    says when the ceiling lifts — a cap that only says "no" teaches nothing.
    """
    cap = cap_usd()
    if cap <= 0:
        return (False, "")
    if free:
        # A free call spends nothing. Blocking it would protect a budget from
        # a cost that does not exist.
        return (False, "")
    if not is_priced(provider, model):
        return (
            True,
            f"{provider}/{model} is a paid provider ABS has no price for, so it "
            f"cannot be counted against your ${cap:.2f} daily ceiling. Add its "
            f"pricing, or turn the ceiling off deliberately.",
        )
    already = spent_today(tenant_id)
    estimate = estimate_cost_usd(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    if already + estimate > cap:
        mins = minutes_to_reset()
        hours, rest = divmod(mins, 60)
        when = f"{hours}h {rest}m" if hours else f"{rest}m"
        return (
            True,
            f"This would put today's spend past your ${cap:.2f} ceiling "
            f"(${already:.4f} used, about ${estimate:.4f} more). The ceiling "
            f"resets at midnight UTC, in {when}.",
        )
    return (False, "")


def status(tenant_id: Optional[str] = "default") -> dict:
    """What the panel shows. `exact` is false when anything went unpriced."""
    with _lock:
        day = dict(_get(tenant_id))
    cap = cap_usd()
    return {
        "spent_usd": round(float(day["usd"]), 6),
        "cap_usd": cap,
        "capped": cap > 0,
        "calls": int(day["calls"]),
        # An estimate built partly from calls we could not price is a floor,
        # and saying so is the difference between a figure and a claim.
        "exact": int(day["unpriced_calls"]) == 0,
        "unpriced_calls": int(day["unpriced_calls"]),
        "resets_in_minutes": minutes_to_reset(),
    }


def reset(tenant_id: Optional[str] = "default") -> None:
    """Tests only."""
    with _lock:
        _state.pop(_key(tenant_id), None)
