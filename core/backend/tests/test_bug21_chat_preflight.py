# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""BUG-21 — chat preflight gate uses cached license state and triggers
a synchronous heartbeat refresh when the cache is stale.

The cache live on disk at ``STATE_PATH``; we monkeypatch it to a tmp
file so the real ``/app/data/license_activation.json`` is untouched.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api import chat as chat_mod
from app.licensing import phone_home


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    state_path = tmp_path / "license_activation.json"
    monkeypatch.setattr(phone_home, "STATE_PATH", state_path)
    # Disable test-mode bypass so the gate actually runs.
    monkeypatch.delenv("ABS_TEST_MODE", raising=False)
    monkeypatch.delenv("ABS_LICENSE_GATE_DISABLED", raising=False)
    # _assert_license_ok() short-circuits when demo mode is active. The session
    # boots with an empty license → demo auto-on, and demo-state can leak in
    # from earlier tests, which would silently bypass the license gate these
    # tests exercise. Pin demo OFF so the license path always runs (isolation).
    monkeypatch.setattr("app.licensing.demo.is_active", lambda: False)
    return state_path


def _write_state(path: Path, *, valid: bool, age_secs: float, reason: str = "ok"):
    last = datetime.now(timezone.utc) - timedelta(seconds=age_secs)
    path.write_text(
        json.dumps({"valid": valid, "reason": reason, "last_check": last.isoformat()})
    )


def test_gate_passes_when_cache_fresh_and_valid(tmp_state, monkeypatch):
    _write_state(tmp_state, valid=True, age_secs=5)
    # No sync heartbeat should be triggered (cache is fresh).
    monkeypatch.setattr(
        chat_mod,
        "force_heartbeat_sync",
        lambda *a, **kw: pytest.fail("sync HB should not run on fresh cache"),
    )
    chat_mod._assert_license_ok()  # no raise


def test_gate_blocks_when_cache_says_invalid(tmp_state, monkeypatch):
    _write_state(tmp_state, valid=False, age_secs=5, reason="revoked")
    monkeypatch.setattr(chat_mod, "force_heartbeat_sync", lambda *a, **kw: None)

    with pytest.raises(HTTPException) as exc_info:
        chat_mod._assert_license_ok()
    assert exc_info.value.status_code == 403
    assert "license_revoked" in str(exc_info.value.detail)


def test_gate_triggers_sync_hb_when_stale(tmp_state, monkeypatch):
    _write_state(tmp_state, valid=True, age_secs=120)  # > 30s threshold

    called = {"n": 0}

    def fake_sync():
        called["n"] += 1
        return {
            "valid": False,
            "reason": "revoked_by_admin",
            "last_check": datetime.now(timezone.utc).isoformat(),
        }

    monkeypatch.setattr(chat_mod, "force_heartbeat_sync", fake_sync)

    with pytest.raises(HTTPException) as exc_info:
        chat_mod._assert_license_ok()
    assert called["n"] == 1
    assert "revoked_by_admin" in str(exc_info.value.detail)


def test_gate_fail_closed_when_no_state_and_no_refresh(tmp_state, monkeypatch):
    # No state file written → cache empty → sync HB returns None (offline).
    monkeypatch.setattr(chat_mod, "force_heartbeat_sync", lambda *a, **kw: None)

    with pytest.raises(HTTPException) as exc_info:
        chat_mod._assert_license_ok()
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "license_not_activated"


def test_gate_test_mode_bypass(tmp_state, monkeypatch):
    monkeypatch.setenv("ABS_TEST_MODE", "1")
    # Even with no state and never-activated, test-mode bypass returns silently.
    chat_mod._assert_license_ok()


def test_gate_disabled_env_bypass(tmp_state, monkeypatch):
    monkeypatch.setenv("ABS_LICENSE_GATE_DISABLED", "1")
    chat_mod._assert_license_ok()


def test_get_cached_license_state_returns_dict(tmp_state):
    assert phone_home.get_cached_license_state() == {}
    _write_state(tmp_state, valid=True, age_secs=1)
    state = phone_home.get_cached_license_state()
    assert state.get("valid") is True


def test_force_heartbeat_sync_cooldown(tmp_state, monkeypatch):
    """Two back-to-back sync calls — only the first should attempt HTTP."""
    monkeypatch.setattr(phone_home, "_last_sync_hb_ts", 0.0)

    from app.config import settings

    monkeypatch.setattr(settings, "license_key", "dummy.jwt.token")
    monkeypatch.setattr(
        phone_home,
        "collect_machine_fingerprint",
        lambda: "fp" * 32,
        raising=False,
    )

    calls = {"n": 0}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **kw):
            calls["n"] += 1

            class R:
                @staticmethod
                def raise_for_status():
                    pass

                @staticmethod
                def json():
                    return {"valid": True, "reason": "ok"}

            return R()

    monkeypatch.setattr(phone_home.httpx, "Client", FakeClient)

    first = phone_home.force_heartbeat_sync(timeout_s=1.0)
    second = phone_home.force_heartbeat_sync(timeout_s=1.0)

    assert first is not None
    assert second is None  # cooldown
    assert calls["n"] == 1
