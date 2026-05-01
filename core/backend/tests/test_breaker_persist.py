"""014 — Circuit breaker state persist testleri."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


@pytest.fixture
def isolated_breaker_dir(monkeypatch, tmp_path: Path):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


def test_save_load_roundtrip(isolated_breaker_dir):
    from app.cascade.persist import load, save

    states = {
        "groq": {"state": "open", "fail_count": 5, "opened_at_real_time": time.time()},
        "anthropic": {
            "state": "half_open",
            "fail_count": 5,
            "opened_at_real_time": time.time(),
        },
    }
    save(states)
    restored = load()
    assert set(restored.keys()) == {"groq", "anthropic"}
    assert restored["groq"]["state"] == "open"
    assert restored["anthropic"]["state"] == "half_open"


def test_restore_skips_expired_open(isolated_breaker_dir):
    from app.cascade.breaker import CircuitBreaker
    from app.cascade.persist import save

    save(
        {
            "groq": {
                "state": "open",
                "fail_count": 5,
                "opened_at_real_time": time.time() - 120,
            }
        }
    )
    b = CircuitBreaker(reset_timeout_seconds=60.0)
    restored = b.restore_state()
    assert restored == 0
    assert "groq" not in b._states


def test_restore_keeps_recent_open(isolated_breaker_dir):
    from app.cascade.breaker import CircuitBreaker
    from app.cascade.persist import save

    save(
        {
            "groq": {
                "state": "open",
                "fail_count": 5,
                "opened_at_real_time": time.time() - 30,
            }
        }
    )
    b = CircuitBreaker(reset_timeout_seconds=60.0)
    restored = b.restore_state()
    assert restored == 1
    assert b._states["groq"].state == "open"


@pytest.mark.asyncio
async def test_persist_called_after_failure(isolated_breaker_dir):
    """5 record_failure sonrasi diskte open state JSON dosyasi olusur."""
    from app.cascade.breaker import CircuitBreaker

    b = CircuitBreaker(fail_threshold=5, fail_window_seconds=600.0)
    for _ in range(5):
        await b.record_failure("test_provider")

    state_file = isolated_breaker_dir / "breaker_state.json"
    assert state_file.is_file()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert "test_provider" in data["states"]
    assert data["states"]["test_provider"]["state"] == "open"


@pytest.mark.asyncio
async def test_record_success_persists_closed_skip(isolated_breaker_dir):
    """record_success closed yapar, dosyada open state olmaz."""
    from app.cascade.breaker import CircuitBreaker

    b = CircuitBreaker(fail_threshold=2)
    await b.record_failure("p1")
    await b.record_failure("p1")
    state_file = isolated_breaker_dir / "breaker_state.json"
    assert state_file.is_file()
    # success → closed → persist boşalır
    await b.record_success("p1")
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["states"] == {}
