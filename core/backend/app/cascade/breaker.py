# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Circuit breaker — provider bazlı hata sayacı."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Literal

State = Literal["closed", "open", "half_open"]


@dataclass
class _ProviderState:
    state: State = "closed"
    fail_count: int = 0
    fail_window_start: float = 0.0
    opened_at: float = 0.0


class CircuitBreaker:
    """5 hata/60s → open; 60s reset sonra half-open; başarıyla closed'a geri."""

    def __init__(
        self,
        *,
        fail_threshold: int = 5,
        fail_window_seconds: float = 60.0,
        reset_timeout_seconds: float = 60.0,
    ) -> None:
        self.fail_threshold = fail_threshold
        self.fail_window_seconds = fail_window_seconds
        self.reset_timeout_seconds = reset_timeout_seconds
        self._states: Dict[str, _ProviderState] = {}
        self._lock = asyncio.Lock()

    def _now(self) -> float:
        return time.monotonic()

    async def allow(self, provider: str) -> bool:
        """Provider şu an çağrılabilir mi?"""
        async with self._lock:
            s = self._states.setdefault(provider, _ProviderState())
            if s.state == "open":
                if self._now() - s.opened_at >= self.reset_timeout_seconds:
                    s.state = "half_open"
                    return True
                return False
            # closed veya half_open → geç
            return True

    async def record_success(self, provider: str) -> None:
        async with self._lock:
            s = self._states.setdefault(provider, _ProviderState())
            s.state = "closed"
            s.fail_count = 0
            s.fail_window_start = 0.0
            s.opened_at = 0.0
        self._persist()

    async def record_failure(self, provider: str) -> None:
        async with self._lock:
            s = self._states.setdefault(provider, _ProviderState())
            now = self._now()
            # pencere dışıysa sayacı sıfırla
            if s.fail_window_start == 0.0 or now - s.fail_window_start > self.fail_window_seconds:
                s.fail_count = 1
                s.fail_window_start = now
            else:
                s.fail_count += 1
            # half_open'da tek fail → tekrar open
            if s.state == "half_open":
                s.state = "open"
                s.opened_at = now
                self._persist()
                return
            if s.fail_count >= self.fail_threshold:
                s.state = "open"
                s.opened_at = now
        self._persist()

    def restore_state(self) -> int:
        """014 — Disk'ten breaker state yukle. Eski/expired open'lar atlanir."""
        from app.cascade.persist import load

        saved = load()
        restored = 0
        now_mono = self._now()
        for provider, s in saved.items():
            if s.get("state") not in ("open", "half_open"):
                continue
            opened_real = float(s.get("opened_at_real_time", 0) or 0)
            elapsed = time.time() - opened_real
            if elapsed >= self.reset_timeout_seconds:
                continue  # zaten reset, restore etme
            self._states[provider] = _ProviderState(
                state=s.get("state", "open"),
                fail_count=int(s.get("fail_count", self.fail_threshold)),
                opened_at=now_mono,  # monotonic re-baseline
            )
            restored += 1
        return restored

    def _persist(self) -> None:
        """Acik/half-open state'leri persist (closed'lar yazilmaz)."""
        try:
            from app.cascade.persist import save

            snapshot_data: Dict[str, dict] = {}
            for provider, ps in self._states.items():
                if ps.state in ("open", "half_open"):
                    snapshot_data[provider] = {
                        "state": ps.state,
                        "fail_count": ps.fail_count,
                        "opened_at_real_time": time.time(),
                    }
            save(snapshot_data)
        except Exception:  # pragma: no cover — persist non-fatal
            pass

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        return {
            name: {
                "state": s.state,
                "fail_count": s.fail_count,
                "opened_at": s.opened_at,
            }
            for name, s in self._states.items()
        }


# modul-level singleton
default_breaker = CircuitBreaker()
