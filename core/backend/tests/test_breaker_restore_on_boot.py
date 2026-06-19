# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""3rd-eye audit — circuit-breaker state must survive a restart.

The breaker persists every open/half-open transition to disk (014, persist.py)
and ``restore_state()`` reloads it, but the restore was never wired into the
app's startup lifespan — so the documented "open state survives restart"
guarantee silently never fired. These tests pin both the restore semantics and
the boot wiring so it can't regress.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.cascade import persist
from app.cascade.breaker import CircuitBreaker
from app.config import settings


def test_restore_state_reopens_recent_persisted_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A provider that tripped just before a restart stays isolated."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    persist.save(
        {"groq": {"state": "open", "fail_count": 5,
                  "opened_at_real_time": time.time() - 1}}
    )
    br = CircuitBreaker()
    assert br.restore_state() == 1
    # restored open within the reset window → calls are still blocked
    assert asyncio.run(br.allow("groq")) is False


def test_restore_state_skips_expired_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """An open that already outlived the reset window is NOT restored."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    persist.save(
        {"groq": {"state": "open", "fail_count": 5,
                  "opened_at_real_time": time.time() - 99_999}}
    )
    br = CircuitBreaker()
    assert br.restore_state() == 0
    assert asyncio.run(br.allow("groq")) is True


def test_lifespan_wires_breaker_restore() -> None:
    """Regression: the startup lifespan must call restore_state so the
    persisted state is actually reloaded on boot (it previously wasn't)."""
    import inspect

    from app import main

    src = inspect.getsource(main.lifespan)
    assert "restore_state()" in src, (
        "app.main.lifespan must call default_breaker.restore_state() on boot"
    )
