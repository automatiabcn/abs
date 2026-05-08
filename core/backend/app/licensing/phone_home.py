# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Online activation + heartbeat phone-home (Q12 IP-Hardening R2).

Calls https://license.automatiabcn.com on boot and once per 24h. The URL
is hardcoded — env override would be a tampering vector. Behaviour is
**fail-open within a 7-day grace window**: if the activation server is
unreachable, the instance keeps operating on cached state. After 7 days
of consecutive failures the cached `valid` flag flips to False and the
quota_monitor blocks paid providers.

Persisted state lives at ``/app/data/license_activation.json`` (writable
by the abs uid 1000 user; mounted volume in docker compose).
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Hardcoded — see PROMISE.md / IP-Hardening R2 spec section 8.
# 2026-05-08: deployed on Cloudflare Workers (KV-backed). When
# automatiabcn.com migrates to Cloudflare DNS, swap this for the custom
# domain `license.automatiabcn.com` (Worker route already maps both).
ACTIVATION_URL = "https://abs-license-activation.automatiaabs.workers.dev/v1/activate"
HEARTBEAT_URL = "https://abs-license-activation.automatiaabs.workers.dev/v1/heartbeat"
STATE_PATH = Path("/app/data/license_activation.json")

# 7-day fail-open window (in days). After this, paid providers are blocked.
OFFLINE_GRACE_DAYS = 7

_HTTP_TIMEOUT = 10.0


def _extract_jti(license_token: str) -> str:
    """Decode JWT payload without signature check just to read the jti.

    Used purely as an opaque identifier for the activation server's KV
    store — the real signature check happens in `verify_license`.
    """

    try:
        import jwt

        unverified = jwt.decode(license_token, options={"verify_signature": False})
        return str(unverified.get("jti", "unknown"))
    except Exception:
        return "unknown"


def _read_build_hash() -> str:
    """Read the build hash embedded into the image at build time (R3)."""

    return os.environ.get("ABS_BUILD_HASH", "unknown")


def _instance_url() -> str:
    """Best-effort instance identifier sent to the activation server."""

    try:
        from app.config import settings

        return getattr(settings, "domain", "") or "unknown"
    except Exception:
        return "unknown"


def _persist_activation_state(data: dict[str, Any]) -> None:
    """Persist activation state with a monotonic anchor for grace.

    Patch B (2026-05-08, VULN-R3-02) — pilot Round 3 found the previous
    wall-clock-only check could be bypassed by rolling the system clock
    backward (or restoring a VM snapshot). We now persist
    ``monotonic_anchor_ns`` alongside ``last_check`` and reset
    ``activation_age_secs`` to 0 on every successful server response —
    a successful heartbeat means we're live, so the offline-grace age
    starts over. ``_check_offline_grace`` then takes the maximum of
    wall-clock age and monotonic age; the attacker can shrink the
    wall-clock half but cannot shrink the monotonic counter within the
    same boot, and a negative wall-clock age (clock rollback) is
    rejected outright.
    """

    record = {
        **data,
        "last_check": datetime.now(timezone.utc).isoformat(),
        "monotonic_anchor_ns": time.monotonic_ns(),
        "activation_age_secs": 0,
    }
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(record))
    except OSError as exc:
        logger.warning("activation_state_persist_failed: %s", exc)


def _load_activation_state() -> dict[str, Any] | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("activation_state_load_failed: %s", exc)
        return None


def _check_offline_grace(exc: Exception) -> dict[str, Any]:
    """Decide whether to fail-open during a phone-home outage.

    Two age signals are combined:

    * **Wall clock** — ``now() - last_check``. Truth across container
      restarts. Negative age means the host clock was rolled backward
      (or last_check was written by a future clock); reject outright
      with reason ``offline_grace_clock_drift`` (VULN-R3-02 fix).
    * **Monotonic** — ``activation_age_secs + (now_mono - anchor)``.
      Immune to wall-clock manipulation within the current boot.
      Pre-patch state files lack the anchor; treated as 0 so the
      wall-clock signal still gates them after migration.

    The grace window is exceeded if **either** signal exceeds the
    7-day threshold (``max`` of both), so an attacker cannot shrink
    the reported age by manipulating just one clock source.
    """

    state = _load_activation_state()
    if not state:
        logger.warning("activation_never_succeeded: %s", exc)
        return {"valid": False, "reason": "never_activated"}

    try:
        last_seen = datetime.fromisoformat(state["last_check"])
    except (KeyError, ValueError):
        return {"valid": False, "reason": "never_activated"}

    now = datetime.now(timezone.utc)
    wall_age_secs = (now - last_seen).total_seconds()

    # Patch B — clock rollback / future last_check rejected outright.
    if wall_age_secs < 0:
        logger.warning(
            "offline_grace_clock_drift wall_age_secs=%.0f last_check=%s",
            wall_age_secs,
            state.get("last_check"),
        )
        return {"valid": False, "reason": "offline_grace_clock_drift"}

    # Monotonic anchor (only meaningful within the current boot).
    prev_anchor = state.get("monotonic_anchor_ns")
    prev_age = float(state.get("activation_age_secs", 0) or 0)
    if prev_anchor is None:
        # Pre-patch state — no anchor available. Wall-clock alone gates
        # this state file; the next successful heartbeat re-persists
        # with both fields populated.
        mono_age_secs = 0.0
    else:
        try:
            elapsed_secs = max(0.0, (time.monotonic_ns() - int(prev_anchor)) / 1e9)
        except (TypeError, ValueError):
            elapsed_secs = 0.0
        mono_age_secs = prev_age + elapsed_secs

    total_age_secs = max(wall_age_secs, mono_age_secs)
    threshold_secs = OFFLINE_GRACE_DAYS * 86400

    if total_age_secs > threshold_secs:
        logger.warning(
            "offline_grace_expired age_secs=%.0f threshold=%d",
            total_age_secs,
            threshold_secs,
        )
        return {"valid": False, "reason": "offline_grace_expired"}

    age_days = total_age_secs / 86400
    logger.info("activation_offline_grace age_days=%.1f", age_days)
    return {**state, "valid": True, "reason": f"offline_grace ({age_days:.1f}d)"}


async def activate_online(license_token: str, machine_fp: str) -> dict[str, Any]:
    """First-boot activation call. See module docstring for grace policy."""

    payload = {
        "jti": _extract_jti(license_token),
        "machine_fp": machine_fp,
        "build_hash": _read_build_hash(),
        "instance_url": _instance_url(),
        "timestamp": int(time.time()),
    }

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(ACTIVATION_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return _check_offline_grace(exc)

    _persist_activation_state(data)
    return data


async def heartbeat_online(license_token: str, machine_fp: str) -> dict[str, Any]:
    """Periodic (24h) liveness ping. Same fail-open policy as activate."""

    payload = {
        "jti": _extract_jti(license_token),
        "machine_fp": machine_fp,
        "build_hash": _read_build_hash(),
        "timestamp": int(time.time()),
    }

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(HEARTBEAT_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return _check_offline_grace(exc)

    _persist_activation_state(data)
    return data
