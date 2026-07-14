# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Patch B — VULN-R3-02 offline-grace clock-rollback hardening tests.

Pilot This change found that ``_check_offline_grace`` used wall-clock
arithmetic only: rolling the host clock backward (or restoring a VM
snapshot) yielded a negative age, which compared ``False`` against
the 7-day threshold and kept the grace window valid forever. Patch B
(2026-05-08) adds:

1. Monotonic-counter accumulator persisted alongside ``last_check`` so
   age cannot be shrunk by manipulating only the wall clock.
2. Negative wall-clock age rejected outright as
   ``offline_grace_clock_drift``.

These three tests lock the new behaviour in place.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from app.licensing import phone_home as ph_mod


def test_offline_grace_clock_drift_negative_age_rejected(tmp_path, monkeypatch):
    """Attacker rolls system clock backward 10 days → ``last_check``
    sits 10 days in the future → wall-clock age is negative → grace
    is invalid with reason ``offline_grace_clock_drift``."""

    state_path = tmp_path / "license_activation.json"
    future_last_check = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    state_path.write_text(
        json.dumps(
            {
                "valid": True,
                "watermark": "wm123",
                "last_check": future_last_check,
            }
        )
    )
    monkeypatch.setattr(ph_mod, "STATE_PATH", state_path)

    result = ph_mod._check_offline_grace(RuntimeError("synthetic_outage"))

    assert result["valid"] is False
    assert result["reason"] == "offline_grace_clock_drift"


def test_offline_grace_monotonic_anchor_within_window(tmp_path, monkeypatch):
    """6-day cumulative monotonic age + fresh wall clock ⇒ still inside
    the 7-day grace window. Verifies the new monotonic accumulator
    keeps grace open when the host has been offline for 6 days."""

    state_path = tmp_path / "license_activation.json"
    six_days_ns = 6 * 86400 * 1_000_000_000
    anchor = time.monotonic_ns() - six_days_ns
    state_path.write_text(
        json.dumps(
            {
                "valid": True,
                "watermark": "wm123",
                "last_check": datetime.now(timezone.utc).isoformat(),
                "monotonic_anchor_ns": anchor,
                "activation_age_secs": 0,
            }
        )
    )
    monkeypatch.setattr(ph_mod, "STATE_PATH", state_path)

    result = ph_mod._check_offline_grace(RuntimeError("synthetic_outage"))

    assert result["valid"] is True
    assert "offline_grace" in result["reason"]


def test_offline_grace_monotonic_anchor_expired(tmp_path, monkeypatch):
    """8-day cumulative monotonic age exceeds the 7-day window even
    though the wall clock is fresh — attacker who freezes the wall
    clock (or rolls it back to a recent value) cannot shrink the
    monotonic counter, so grace must reject."""

    state_path = tmp_path / "license_activation.json"
    eight_days_secs = 8 * 86400
    state_path.write_text(
        json.dumps(
            {
                "valid": True,
                "watermark": "wm123",
                # Wall clock looks fresh — only the monotonic counter
                # exposes the 8 days that actually elapsed.
                "last_check": datetime.now(timezone.utc).isoformat(),
                "monotonic_anchor_ns": time.monotonic_ns(),
                "activation_age_secs": eight_days_secs,
            }
        )
    )
    monkeypatch.setattr(ph_mod, "STATE_PATH", state_path)

    result = ph_mod._check_offline_grace(RuntimeError("synthetic_outage"))

    assert result["valid"] is False
    assert result["reason"] == "offline_grace_expired"
