# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Tier-1 sandbox — the isolation the OS already provides.

These tests pin the two rules the design rests on: it fails CLOSED (no
isolation means no run, because an agent that can turn its own sandbox off is
not sandboxed), and it always names the mechanism that actually ran the
command (a caller who believes it ran confined when it did not is worse off
than one who knows it has none).
"""

from __future__ import annotations

import os
import platform

import pytest

from app.sandbox import runner


@pytest.fixture()
def ws(tmp_path):
    return str(tmp_path)


def _skip_unless_sandboxed():
    if not runner.available_mechanism():
        pytest.skip("no OS sandbox on this platform")


def test_no_isolation_means_no_run(monkeypatch, ws):
    """Fail closed. Running unconfined would make every 'sandboxed' label a
    lie, and the field evidence is an agent that switched its own sandbox off
    when a denylist got in the way."""
    monkeypatch.setattr(runner, "available_mechanism", lambda: "")
    res = runner.run(["/bin/echo", "hi"], workspace_root=ws)
    assert res.ok is False
    assert res.exit_code is None
    assert "refusing to run unconfined" in res.refused


def test_the_result_always_names_the_mechanism(ws):
    _skip_unless_sandboxed()
    res = runner.run(["/bin/echo", "hi"], workspace_root=ws)
    assert res.mechanism in ("seatbelt", "bubblewrap")
    assert res.ok is True


def test_a_missing_workspace_is_refused_not_guessed(tmp_path):
    res = runner.run(["/bin/echo", "hi"], workspace_root=str(tmp_path / "nope"))
    assert res.ok is False
    assert "workspace not found" in res.refused


def test_it_can_write_inside_the_workspace(ws):
    _skip_unless_sandboxed()
    res = runner.run(
        ["/bin/sh", "-c", "echo hello > inside.txt && cat inside.txt"],
        workspace_root=ws,
    )
    assert res.ok is True, res.stderr
    assert "hello" in res.stdout
    assert os.path.exists(os.path.join(ws, "inside.txt"))


def test_it_cannot_write_outside_the_workspace(ws, tmp_path):
    """The boundary that matters for an agent is what it can WRITE."""
    _skip_unless_sandboxed()
    target = tmp_path.parent / "abs-escape-should-not-exist.txt"
    res = runner.run(
        ["/bin/sh", "-c", f"echo escaped > {target}"], workspace_root=ws
    )
    assert res.ok is False
    assert not target.exists(), "the sandbox let a write escape the workspace"


def test_network_is_off_unless_asked_for(ws):
    """A build that suddenly wants the network is exactly the moment worth
    interrupting a developer over — so it is off by default."""
    _skip_unless_sandboxed()
    if not os.path.exists("/usr/bin/curl"):
        pytest.skip("curl not available")
    res = runner.run(
        ["/usr/bin/curl", "-s", "-m", "4", "https://example.com"], workspace_root=ws
    )
    assert res.ok is False, "network reached the outside with allow_network=False"


def test_secrets_do_not_travel_into_the_sandbox(ws, monkeypatch):
    """An agent that never sees a secret cannot leak one."""
    _skip_unless_sandboxed()
    monkeypatch.setenv("ABS_SECRET_TOKEN", "super-secret-value")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "also-secret")
    res = runner.run(["/usr/bin/env"], workspace_root=ws)
    assert res.ok is True, res.stderr
    assert "super-secret-value" not in res.stdout
    assert "also-secret" not in res.stdout
    assert "ABS_SECRET_TOKEN" not in res.env_allowed


def test_a_hanging_command_is_stopped_and_says_so(ws):
    _skip_unless_sandboxed()
    res = runner.run(["/bin/sleep", "30"], workspace_root=ws, timeout=1.0)
    assert res.ok is False
    assert "timed out" in res.refused
    assert res.mechanism, "even a timeout says which isolation was used"


def test_an_empty_command_is_refused():
    res = runner.run([], workspace_root="/tmp")
    assert res.ok is False
    assert "no command" in res.refused


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS profile")
def test_the_macos_profile_denies_by_default(ws):
    """An inverted default cannot be patched safe — that is how the 2026
    sandbox escapes happened. The profile must start closed."""
    profile = runner._seatbelt_profile(ws, allow_network=False)
    assert profile.splitlines()[1] == "(deny default)"
    assert "(allow network*)" not in profile
    assert ws in profile, "the workspace must be the writable subpath"


def test_the_mcp_tools_are_registered():
    import asyncio

    from app.mcp.server import mcp_server

    names = {t.name for t in asyncio.run(mcp_server.list_tools())}
    assert {"sandbox_run", "sandbox_status"} <= names


def test_only_recognised_checks_may_run(ws):
    """An allowlist of whole programs is the control — the 2026 escapes were
    written by people who knew every denylist entry."""
    import asyncio
    import json

    from app.mcp.tools import sandbox_tools

    out = json.loads(
        asyncio.run(sandbox_tools.sandbox_run("curl https://evil.example", ws))
    )
    assert out["ok"] is False
    assert "not one of the checks" in out["refused"]

    installer = json.loads(
        asyncio.run(sandbox_tools.sandbox_run("pip install requests", ws))
    )
    assert installer["ok"] is False, "installing is not a check"


def test_status_says_whether_running_is_possible_at_all():
    """A panel must be able to ask BEFORE offering a Run button."""
    import asyncio
    import json

    from app.mcp.tools import sandbox_tools

    out = json.loads(asyncio.run(sandbox_tools.sandbox_status()))
    assert out["can_run"] == bool(out["mechanism"])
    assert out["installs_required"] == [], "Tier 1 must require no installs"
