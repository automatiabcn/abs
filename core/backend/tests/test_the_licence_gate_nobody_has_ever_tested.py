# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The licence gate — the one thing 2900 tests never touch.

`conftest` sets `ABS_TEST_MODE=1` for the whole session, and `_assert_license_ok`
returns immediately when it sees it. So every test in this repository exercises an
*unlicensed* application: the gate that stands between a customer and the chat box —
the product's front door — has never once been opened in anger by the suite.

That is how a 403 on the first minute of a clean install stayed invisible while the
suite was green. These tests turn the flag off and drive the gate as a customer meets
it, so its behaviour is written down rather than assumed:

  * no activation state and no reachable activation server → refused (fail-closed,
    and this is what a clean install hits today, because `license.automatiabcn.com`
    has no DNS record);
  * a valid cached state → allowed;
  * a revoked state → refused, with the reason;
  * a stale cache (older than 30s) → one synchronous heartbeat before deciding.

Whether the gate *should* be this strict is a product decision. What it does is not
a matter of opinion, and now it is not a matter of guesswork either.
"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from app.api import chat as chat_api


@pytest.fixture
def licensed_app(monkeypatch):
    """The application as a customer runs it: no test-mode escape hatch."""
    monkeypatch.delenv("ABS_TEST_MODE", raising=False)
    monkeypatch.delenv("ABS_LICENSE_GATE_DISABLED", raising=False)
    # Demo mode is a separate door (app/licensing/demo). Keep it shut here.
    monkeypatch.setattr("app.licensing.demo.is_active", lambda: False, raising=False)
    yield
    os.environ["ABS_TEST_MODE"] = "1"


def _state(monkeypatch, state, age, refreshed="__unset__"):
    monkeypatch.setattr(chat_api, "get_cached_license_state", lambda: state)
    monkeypatch.setattr(chat_api, "cache_age_seconds", lambda: age)
    if refreshed != "__unset__":
        monkeypatch.setattr(chat_api, "force_heartbeat_sync", lambda: refreshed)


def test_a_valid_licence_opens_the_door(licensed_app, monkeypatch):
    _state(monkeypatch, {"valid": True}, 5.0)
    chat_api._assert_license_ok()  # does not raise


def test_a_never_activated_server_is_refused(licensed_app, monkeypatch):
    """Fail-closed, by design. It is also what a clean install gets today: the
    activation host has no DNS record, so the heartbeat cannot succeed and chat —
    the product's whole surface — answers 403 within the first minute."""
    _state(monkeypatch, None, None, refreshed=None)

    with pytest.raises(HTTPException) as exc:
        chat_api._assert_license_ok()

    assert exc.value.status_code == 403
    assert exc.value.detail == "license_not_activated"


def test_a_revoked_licence_is_refused_and_says_why(licensed_app, monkeypatch):
    _state(monkeypatch, {"valid": False, "reason": "refunded"}, 5.0)

    with pytest.raises(HTTPException) as exc:
        chat_api._assert_license_ok()

    assert exc.value.status_code == 403
    assert exc.value.detail == "license_revoked:refunded"


def test_a_cache_older_than_thirty_seconds_is_refreshed_before_deciding(
    licensed_app, monkeypatch
):
    """A revoke has to reach a running server quickly; a 30-second-old yes is not
    good enough to keep answering on."""
    calls: list = []

    monkeypatch.setattr(chat_api, "get_cached_license_state", lambda: {"valid": True})
    monkeypatch.setattr(chat_api, "cache_age_seconds", lambda: 31.0)

    def _heartbeat():
        calls.append(1)
        return {"valid": False, "reason": "revoked_upstream"}

    monkeypatch.setattr(chat_api, "force_heartbeat_sync", _heartbeat)

    with pytest.raises(HTTPException) as exc:
        chat_api._assert_license_ok()

    assert calls == [1], "a stale cache was trusted without asking"
    assert exc.value.detail == "license_revoked:revoked_upstream"


def test_a_fresh_cache_is_not_re_checked_on_every_message(licensed_app, monkeypatch):
    """The other half: a heartbeat per message would put the activation server in
    the request path of every chat turn."""
    calls: list = []

    monkeypatch.setattr(chat_api, "get_cached_license_state", lambda: {"valid": True})
    monkeypatch.setattr(chat_api, "cache_age_seconds", lambda: 1.0)
    monkeypatch.setattr(
        chat_api, "force_heartbeat_sync", lambda: calls.append(1) or {"valid": True}
    )

    chat_api._assert_license_ok()

    assert calls == []


def test_the_test_mode_flag_is_the_only_thing_holding_the_door_open(monkeypatch):
    """Named plainly, because it is the reason none of the above was known.

    Every one of the ~2900 tests in this suite runs with ABS_TEST_MODE=1, and the
    gate's first line is `if ABS_TEST_MODE == "1": return`. The suite tests an
    application with no licensing in it."""
    monkeypatch.setenv("ABS_TEST_MODE", "1")
    monkeypatch.setattr(chat_api, "get_cached_license_state", lambda: None)
    monkeypatch.setattr(chat_api, "cache_age_seconds", lambda: None)

    chat_api._assert_license_ok()  # no state at all, and still allowed
