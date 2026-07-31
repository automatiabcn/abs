# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The sandbox tiers, and the one rule they all answer to: nothing is
claimed before it is proven on this machine.

Tier-1 Windows is a WRITE_RESTRICTED token gated behind a live self-test;
Tier-2 is a microVM that today exists only as honest detection. Both must
fail CLOSED — an unproven mechanism reporting available is how "sandboxed"
becomes a label instead of a property.
"""

from __future__ import annotations

import asyncio
import json
import platform

import pytest

from app.sandbox import microvm, runner, windows_token


# --- Windows restricted token ----------------------------------------------


def test_the_token_tier_is_never_available_off_windows(monkeypatch):
    monkeypatch.setattr(windows_token, "_SELF_TEST", None)
    assert windows_token.self_test() is False or platform.system() == "Windows"


def test_an_unproven_windows_reports_no_mechanism(monkeypatch):
    monkeypatch.setattr(runner.platform, "system", lambda: "Windows")
    monkeypatch.setattr(windows_token, "self_test", lambda: False)
    assert runner.available_mechanism() == ""


def test_a_proven_windows_reports_the_token_mechanism(monkeypatch):
    monkeypatch.setattr(runner.platform, "system", lambda: "Windows")
    monkeypatch.setattr(windows_token, "self_test", lambda: True)
    assert runner.available_mechanism() == windows_token.MECHANISM


def test_a_failed_self_test_is_cached_not_retried_forever(monkeypatch):
    calls = []
    monkeypatch.setattr(windows_token, "_SELF_TEST", None)
    monkeypatch.setattr(windows_token.sys, "platform", "win32")

    def _boom(path):
        calls.append(path)
        raise RuntimeError("icacls unavailable")

    monkeypatch.setattr(windows_token, "_grant_restricted_write", _boom)
    assert windows_token.self_test() is False
    assert windows_token.self_test() is False
    assert len(calls) == 1, "the verdict is proven once, then remembered"
    monkeypatch.setattr(windows_token, "_SELF_TEST", None)


# --- network honesty --------------------------------------------------------


def test_only_profile_sandboxes_promise_a_blocked_network():
    assert runner.network_is_blocked("seatbelt") is True
    assert runner.network_is_blocked("bubblewrap") is True
    assert runner.network_is_blocked(windows_token.MECHANISM) is False
    assert runner.network_is_blocked("") is False


def test_sandbox_run_reports_what_the_tier_can_promise(monkeypatch):
    from app.mcp.tools import sandbox_tools as st

    monkeypatch.setattr(
        st._sandbox, "run",
        lambda *a, **k: runner.SandboxResult(
            True, 0, "ok", "", mechanism=windows_token.MECHANISM, duration_ms=3
        ),
    )
    out = json.loads(
        asyncio.run(st.sandbox_run("pytest -q", workspace_root="/tmp"))
    )
    assert out["network"] == "not blocked by this tier", out


# --- microVM tier -----------------------------------------------------------


def test_the_microvm_tier_is_unavailable_until_proven():
    s = microvm.status()
    assert s.available is False, "no helper has ever proven itself here"
    assert s.reason, "an unavailable tier owes the operator its reason"


def test_a_capable_mac_says_what_is_missing(monkeypatch):
    monkeypatch.setattr(microvm.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(microvm.os.path, "exists", lambda p: True)
    monkeypatch.setattr(microvm.shutil, "which", lambda n: None)
    s = microvm.status()
    assert s.platform_capable is True
    assert s.available is False
    assert "not built yet" in s.reason


def test_a_helper_on_path_is_still_only_a_claim(monkeypatch):
    monkeypatch.setattr(microvm.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(microvm.os.path, "exists", lambda p: True)
    monkeypatch.setattr(microvm.shutil, "which", lambda n: "/usr/local/bin/abs-vmhost")
    s = microvm.status()
    assert s.available is False, "found is not proven"
    assert "unproven" in s.reason


def test_sandbox_status_lists_both_tiers(monkeypatch):
    from app.mcp.tools import sandbox_tools as st

    monkeypatch.setattr(st._sandbox, "available_mechanism", lambda: "seatbelt")
    out = json.loads(asyncio.run(st.sandbox_status()))
    tiers = {t["tier"]: t for t in out["tiers"]}
    assert tiers["os-native"]["available"] is True
    assert tiers["os-native"]["network_blocked"] is True
    assert tiers["microvm"]["available"] is False
    assert out["network_blocked"] is True


def test_sandbox_status_says_when_the_network_is_not_blocked(monkeypatch):
    from app.mcp.tools import sandbox_tools as st

    monkeypatch.setattr(
        st._sandbox, "available_mechanism", lambda: windows_token.MECHANISM
    )
    out = json.loads(asyncio.run(st.sandbox_status()))
    assert out["network_blocked"] is False
    assert "NOT blocked" in out["note"]
