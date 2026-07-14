# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The free window, under its old name.

This module used to own a fourteen-day "demo": its own file, its own clock, its
own idea of when the free period ended. Then the product became a monthly
subscription with a seven-day trial, and for a while there were two free windows
running side by side off the same empty licence key — one of them twice as long
as the other, neither aware of the other. That is the same shape of bug as the
gate and the panel disagreeing: one rule, two implementations, and the customer
standing between them.

So the timer is gone. `licensing.trial` is the only clock, and everything here
reads it. What stays is the vocabulary: the settings page, the SSE banner, the
MCP `demo_status` tool and the setup wizard all ask this module questions, and
they keep getting answers — the answers are now simply true.

Nothing here is authoritative. To know whether this server may be used, ask
`licensing.gate`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from app.config import settings
from app.licensing import trial

# Still imported by name elsewhere. The number comes from the trial, because
# there is only one number.
DEMO_DURATION_DAYS = trial.TRIAL_DAYS


def _state_path() -> Path:
    """The legacy state file.

    Still named, because `demo_admin` reads this path and installs from before
    the rename still have the file — `trial._oldest_evidence()` reads its
    `started_at`, so a server that has been running free for ten days does not
    get a brand new week out of a rename.
    """
    p = Path(settings.data_dir) / "demo_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _expiry(started_at: float) -> float:
    return started_at + DEMO_DURATION_DAYS * 86400


def start_demo() -> Dict:
    """Open (or re-report) the free window. Idempotent — asking again does not
    restart the clock, because the clock is not kept here."""
    state = trial.status()
    return {
        "started_at": state.started_at,
        "expires_at": _expiry(state.started_at),
        "duration_days": DEMO_DURATION_DAYS,
    }


def status() -> Dict:
    """Snapshot for the panel banner and the MCP tool. Same shape as it ever was."""
    state = trial.status()
    return {
        "started": True,
        "active": state.active,
        "expired": not state.active,
        "days_remaining": state.days_left,
        "started_at": state.started_at,
        "expires_at": _expiry(state.started_at),
    }


def is_active() -> bool:
    """With no licence, is the free window still open?"""
    if (settings.license_key or "").strip():
        return False
    return trial.status().active


def reset() -> None:
    """Back to a first-run install — test and dev only.

    It clears the trial as well: resetting only the legacy file would reset
    nothing, since nothing reads the legacy file's clock any more.
    """
    for path in (_state_path(), Path(settings.data_dir) / "trial.json"):
        try:
            if path.is_file():
                path.unlink()
        except Exception:  # noqa: BLE001 — best effort, dev only
            pass


def _read_state() -> Optional[Dict]:
    """Legacy accessor. Kept so importers keep working; the truth is `status()`."""
    return status()
