# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""When this server was installed, and how much of its trial is left.

The product is a monthly subscription with a seven-day trial. That sentence has
one hard requirement behind it: the server has to know *when it started*, and it
has to keep knowing across restarts, upgrades and container rebuilds — on a
machine the customer owns and we cannot see.

Three rules, and each one exists because the obvious implementation gets it
wrong:

**The clock only ever moves forward.** The trial's remaining days are computed
from a stored timestamp, and a stored timestamp can be met with a clock that has
been moved backwards. So the file also carries the latest moment this server has
ever seen; if `now` is behind that, the machine's clock has gone back, and we
treat *the last thing we saw* as now. A customer can still reinstall — this is
their box, and nothing running on it can stop them. That is what the licence
agreement is for. What we can refuse to do is be trivially rewound.

**A missing file is not a fresh trial.** Deleting `trial.json` would otherwise
be an infinite trial, one `rm` at a time. When the file is gone but the server is
plainly not new — the setup wizard has been completed, there are meetings in the
database — we date the install from the oldest evidence we can find rather than
from this moment.

**It never blocks and never phones home.** Same rule as the rest of the gate: a
decision about whether the customer may use what they paid for is taken from
local state, in the request path, with no socket in it.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

TRIAL_DAYS = 7
_TRIAL_SECONDS = TRIAL_DAYS * 86400


@dataclass(frozen=True)
class Trial:
    started_at: float
    seconds_left: float

    @property
    def active(self) -> bool:
        return self.seconds_left > 0

    @property
    def days_left(self) -> int:
        """Rounded up: a trial with an hour left has one day left, not zero."""
        if self.seconds_left <= 0:
            return 0
        return max(1, int((self.seconds_left + 86399) // 86400))


def _path() -> Path:
    return Path(settings.data_dir) / "trial.json"


def _read() -> Optional[Dict[str, Any]]:
    try:
        raw = _path().read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("started_at"), (int, float)):
            return data
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001 — a corrupt file is a missing file
        logger.warning("trial_state_unreadable err=%s", exc)
    return None


def _write(started_at: float, high_water: float) -> None:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"started_at": started_at, "seen_at": high_water}),
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception as exc:  # noqa: BLE001 — never fail a request over this
        logger.warning("trial_state_unwritable err=%s", exc)


def _oldest_evidence() -> Optional[float]:
    """This server is not new. When did it start?

    Used when `trial.json` is absent but the install plainly is not — the wizard
    has been through, or there is data in the database. Without this, deleting one
    file is an unlimited supply of trials.
    """
    candidates: list[float] = []

    # The fourteen-day demo this trial replaced. An install that has been running
    # free since before the rename is dated from when *it* started, not from the
    # day it was upgraded — otherwise shipping the subscription would have handed
    # every existing install a fresh week.
    try:
        legacy = json.loads(
            (Path(settings.data_dir) / "demo_state.json").read_text(encoding="utf-8")
        )
        started = legacy.get("started_at")
        if isinstance(started, (int, float)) and started > 0:
            candidates.append(float(started))
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001 — an unreadable legacy file is no evidence
        pass

    try:
        from app.api.setup import read_state

        state = read_state()
        for key in ("started_at", "completed_at"):
            value = state.get(key)
            if isinstance(value, (int, float)) and value > 0:
                candidates.append(float(value))
    except Exception:  # noqa: BLE001
        pass

    # The data directory itself: the wizard's state file is written the first time
    # anyone opens /setup, so its mtime is a floor on the install date.
    try:
        state_file = Path(settings.data_dir) / "setup_state.json"
        if state_file.is_file():
            candidates.append(state_file.stat().st_mtime)
    except Exception:  # noqa: BLE001
        pass

    return min(candidates) if candidates else None


def status() -> Trial:
    """How much trial this install has left. Reads and repairs local state."""
    now = time.time()
    data = _read()

    if data is None:
        started = _oldest_evidence() or now
        _write(started, now)
        if started < now - 60:
            logger.info(
                "trial_state_rebuilt started_at=%.0f (trial.json was missing on an "
                "install that is not new)",
                started,
            )
        return status_from(started, now)

    started = float(data["started_at"])
    seen = float(data.get("seen_at") or started)

    # A clock that has gone backwards does not buy time. The last moment we saw
    # stands in for now, and the high-water mark only ever rises.
    effective_now = max(now, seen)
    if effective_now > seen + 60:
        _write(started, effective_now)

    return status_from(started, effective_now)


def status_from(started_at: float, now: float) -> Trial:
    elapsed = max(0.0, now - started_at)
    return Trial(started_at=started_at, seconds_left=max(0.0, _TRIAL_SECONDS - elapsed))
