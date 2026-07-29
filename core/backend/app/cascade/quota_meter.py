# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Per-tenant provider quota meter — RPD / RPM / 429 backoff, UTC-daily reset.

Feeds the Cost HUD ("how much free quota is left, per provider") and records
real 429s as a cooldown signal. State is tenant-scoped and in-process — correct
for the local single-user sidecar (one process) and a single hosted replica.

Design notes vs the standalone origin:
- No ``/tmp`` + ``fcntl.flock`` global file: that leaked across tenants and
  under-counts on multi-replica. State is keyed ``tenant|provider`` in memory,
  guarded by a lock. (A multi-replica hosted tier should later back this with
  the shared ``usage_log`` DB; the API here stays the same.)
- Limits are *free-tier defaults*, overridable per BYOK key. Nothing here ever
  hard-blocks a call — an unknown provider is simply "no limits, never
  throttled". Selection stays the cascade's job; this only records and reports.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

# Free-tier defaults (approximate; a BYOK key may have different limits). Absent
# providers are treated as unlimited and never throttled.
QUOTA_LIMITS: Dict[str, Dict[str, int]] = {
    "groq": {"rpd": 1000, "rpm": 30},
    "cerebras": {"rpd": 14400, "rpm": 30, "tpd": 1_000_000},
    "cloudflare": {"neurons_pd": 10000, "rpm": 300},
    "gemini": {"rpd": 250, "rpm": 15},
    "cohere": {"rpm": 1000},
    "openrouter": {"rpd": 50, "rpm": 20},
}

_DEFAULT_COOLDOWN_SEC = 60
_MAX_BACKOFF_STEPS = 8

_lock = threading.Lock()
_state: Dict[str, dict] = {}


def _key(tenant_id: Optional[str], provider: str) -> str:
    return f"{(tenant_id or 'default').strip() or 'default'}|{provider}"


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _empty() -> dict:
    return {
        "day": _utc_today(),
        "rpd_used": 0,
        "tpd_used": 0,
        "neurons_used": 0,
        "minute_window": [],  # timestamps in the last 60s
        "cooldown_until": 0.0,
        "consecutive_429": 0,
        "total_requests": 0,
    }


def _get(tenant_id: Optional[str], provider: str) -> dict:
    """Fetch (init on miss) provider state, resetting the daily counters at UTC midnight."""
    p = _state.setdefault(_key(tenant_id, provider), _empty())
    today = _utc_today()
    if p.get("day") != today:
        p["day"] = today
        p["rpd_used"] = 0
        p["tpd_used"] = 0
        p["neurons_used"] = 0
        p["consecutive_429"] = 0
    return p


def _trim(p: dict) -> None:
    now = time.time()
    p["minute_window"] = [t for t in p.get("minute_window", []) if now - t < 60]


def record_usage(
    provider: str,
    *,
    tenant_id: Optional[str] = "default",
    tokens: int = 0,
    status_code: int = 200,
) -> None:
    """Record one call. A 429 sets an exponential cooldown. Never raises."""
    if provider not in QUOTA_LIMITS:
        return
    try:
        with _lock:
            p = _get(tenant_id, provider)
            now = time.time()
            p["total_requests"] += 1
            p["rpd_used"] += 1
            if provider == "cerebras":
                p["tpd_used"] += tokens
            elif provider == "cloudflare":
                p["neurons_used"] += max(1, tokens // 1000)
            p["minute_window"] = list(p.get("minute_window", [])) + [now]
            _trim(p)
            if status_code == 429:
                p["consecutive_429"] += 1
                cooldown = _DEFAULT_COOLDOWN_SEC * min(
                    _MAX_BACKOFF_STEPS, 2 ** (p["consecutive_429"] - 1)
                )
                p["cooldown_until"] = now + cooldown
            elif status_code == 200:
                p["consecutive_429"] = 0
    except Exception:  # pragma: no cover — metering must never raise
        pass


def is_throttled(provider: str, *, tenant_id: Optional[str] = "default") -> Tuple[bool, str]:
    """Is the provider throttled right now? Unknown providers are never throttled."""
    if provider not in QUOTA_LIMITS:
        return (False, "no_limits")
    with _lock:
        p = _get(tenant_id, provider)
        now = time.time()
        if p.get("cooldown_until", 0) > now:
            return (True, f"cooldown_{int(p['cooldown_until'] - now)}s")
        limits = QUOTA_LIMITS[provider]
        _trim(p)
        rpm = limits.get("rpm", 0)
        if rpm and len(p["minute_window"]) >= rpm:
            return (True, f"rpm_full_{rpm}")
        rpd = limits.get("rpd", 0)
        if rpd and p.get("rpd_used", 0) >= rpd:
            return (True, f"rpd_exhausted_{rpd}")
        tpd = limits.get("tpd", 0)
        if tpd and p.get("tpd_used", 0) >= tpd:
            return (True, f"tpd_exhausted_{tpd}")
        neurons = limits.get("neurons_pd", 0)
        if neurons and p.get("neurons_used", 0) >= neurons:
            return (True, f"neurons_exhausted_{neurons}")
        return (False, "ok")


def get_remaining(provider: str, *, tenant_id: Optional[str] = "default") -> dict:
    """Remaining quota for one provider (percent + absolute)."""
    if provider not in QUOTA_LIMITS:
        return {"provider": provider, "limits": "none", "rpd_left": "unlimited"}
    with _lock:
        p = _get(tenant_id, provider)
        limits = QUOTA_LIMITS[provider]
        out: dict = {"provider": provider, "day": p.get("day"), "total_requests": p.get("total_requests", 0)}
        rpd = limits.get("rpd", 0)
        if rpd:
            out["rpd_used"] = p.get("rpd_used", 0)
            out["rpd_left"] = max(0, rpd - p.get("rpd_used", 0))
            out["rpd_percent_remaining"] = round(out["rpd_left"] / rpd * 100, 1)
        else:
            out["rpd_left"] = "unlimited"
        return out


def get_all_status(*, tenant_id: Optional[str] = "default") -> dict:
    """JSON-friendly per-provider snapshot for the Cost HUD."""
    providers = {}
    for provider in QUOTA_LIMITS:
        throttled, reason = is_throttled(provider, tenant_id=tenant_id)
        providers[provider] = {
            **get_remaining(provider, tenant_id=tenant_id),
            "throttled": throttled,
            "throttle_reason": reason,
        }
    return {"day": _utc_today(), "tenant": (tenant_id or "default"), "providers": providers}


def looks_like_rate_limit(message: str) -> bool:
    """Heuristic: does this error text describe a 429 / rate-limit?"""
    return bool(re.search(r"\b429\b|rate.?limit|too many requests|quota", message, re.I))


def reset(*, tenant_id: Optional[str] = None) -> int:
    """Clear meter state. Whole store when tenant_id is None, else one tenant."""
    with _lock:
        if tenant_id is None:
            n = len(_state)
            _state.clear()
            return n
        prefix = f"{(tenant_id or 'default')}|"
        keys = [k for k in _state if k.startswith(prefix)]
        for k in keys:
            del _state[k]
        return len(keys)
