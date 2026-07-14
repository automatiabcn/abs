# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""The chat pre-flight licence check, and the activation cache behind it.

This file used to pin the gate that shipped: read a cached activation state,
and whenever the cache was missing or older than thirty seconds, block the
request on a *synchronous heartbeat* to our activation server. Its own tests
said so out loud — `test_gate_fail_closed_when_no_state_and_no_refresh`
asserted a 403 for an install that had simply never managed to phone home,
which is every fresh install, on its first message.

That behaviour is gone (see `test_the_licence_gate_nobody_has_ever_tested.py`
for the rule that replaced it). What remains here is the half that was always
right: the activation cache is read from disk, and `force_heartbeat_sync` does
not fan a burst of callers out into a storm of HTTP calls.

`force_heartbeat_sync` is no longer reachable from the request path. It stays
because the background heartbeat and the admin re-check still use it.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.api import chat as chat_mod
from app.licensing import phone_home


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    state_path = tmp_path / "license_activation.json"
    monkeypatch.setattr(phone_home, "STATE_PATH", state_path)
    monkeypatch.delenv("ABS_TEST_MODE", raising=False)
    monkeypatch.delenv("ABS_LICENSE_GATE_DISABLED", raising=False)
    # An empty licence key auto-opens demo mode, and demo state can leak in from
    # earlier tests. Pin it shut so the licence path is what runs.
    monkeypatch.setattr("app.licensing.demo.is_active", lambda: False)
    return state_path


def _write_state(path: Path, *, valid: bool, age_secs: float, reason: str = "ok"):
    last = datetime.now(timezone.utc) - timedelta(seconds=age_secs)
    path.write_text(
        json.dumps({"valid": valid, "reason": reason, "last_check": last.isoformat()})
    )


def test_the_preflight_never_calls_the_heartbeat(tmp_state, monkeypatch):
    """The point of the rewrite. Whatever the cache says or does not say, our
    activation server is not in the customer's request path."""
    monkeypatch.setattr(
        phone_home,
        "force_heartbeat_sync",
        lambda *a, **kw: pytest.fail("the chat preflight phoned home"),
    )
    _write_state(tmp_state, valid=True, age_secs=9999)  # stale by the old rule

    chat_mod._assert_license_ok()  # no raise, no call


def test_a_fresh_install_is_not_refused(tmp_state, monkeypatch):
    """No state file at all — never activated. The old gate answered
    `license_not_activated`; this is the 403 that met every new customer."""
    assert not tmp_state.exists()

    chat_mod._assert_license_ok()  # no raise


def test_gate_test_mode_bypass(tmp_state, monkeypatch):
    monkeypatch.setenv("ABS_TEST_MODE", "1")
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
