"""Two editor windows are two projects. The chat answers about the one that
asked, not the one whose heartbeat spoke last.

Audit 2026-08-18: `workspace_set(ws-audit)` from one client, then the running
editor's 60-second heartbeat re-announced RobotMarket under the same account,
and `cascade_ask` answered "vip_total is not defined in this project" with
`used_files` from RobotMarket. One slot per (tenant, user).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.workspace import current as ws


@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    monkeypatch.setattr(ws, "_OPEN", {})
    monkeypatch.setattr(ws, "_LATEST", {})


@pytest.fixture
def two(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    return str(a.resolve()), str(b.resolve())


def test_each_window_keeps_its_own_project(two):
    a, b = two
    ws.set_workspace("t", "u", a, client_id="win-1")
    ws.set_workspace("t", "u", b, client_id="win-2")  # the other window's heartbeat
    assert ws.current_workspace("t", "u", client_id="win-1") == a
    assert ws.current_workspace("t", "u", client_id="win-2") == b


def test_a_root_named_by_the_call_wins_over_any_slot(two):
    a, b = two
    ws.set_workspace("t", "u", b, client_id="win-2")
    assert ws.current_workspace("t", "u", client_id="win-2", explicit_root=a) == a


def test_an_explicit_root_that_is_not_a_directory_is_not_a_project(two):
    a, _b = two
    ws.set_workspace("t", "u", a, client_id="w")
    assert ws.current_workspace("t", "u", client_id="w", explicit_root="/no/such/dir") is None


def test_older_editors_without_a_client_id_get_the_latest_slot(two):
    a, b = two
    ws.set_workspace("t", "u", a)
    ws.set_workspace("t", "u", b, client_id="new-editor")
    assert ws.current_workspace("t", "u") == b
    # And a client the server has never heard of falls back the same way.
    assert ws.current_workspace("t", "u", client_id="unknown-window") == b


def test_closing_one_window_does_not_close_the_other(two):
    a, b = two
    ws.set_workspace("t", "u", a, client_id="win-1")
    ws.set_workspace("t", "u", b, client_id="win-2")
    ws.set_workspace("t", "u", "", client_id="win-2")
    assert ws.current_workspace("t", "u", client_id="win-1") == a
    assert ws.current_workspace("t", "u", client_id="win-2") == a  # falls back to latest live slot


def test_users_do_not_see_each_others_projects(two):
    a, b = two
    ws.set_workspace("t", "alice", a, client_id="w")
    ws.set_workspace("t", "bob", b, client_id="w")
    assert ws.current_workspace("t", "alice", client_id="w") == a
    assert ws.current_workspace("t", "bob", client_id="w") == b


@pytest.mark.asyncio
async def test_cascade_ask_reads_the_root_the_call_names(two, monkeypatch):
    """The tool passes the call's root through — the whole point."""
    import app.mcp.server  # noqa: F401 — circular import guard
    from app.mcp.tools import engine_panel_tools as ept

    a, b = two
    (Path(a) / "only_in_a.py").write_text("def alpha():\n    return 1\n")
    (Path(b) / "only_in_b.py").write_text("def beta():\n    return 2\n")
    ws.set_workspace("default", "", b, client_id="other-window")

    seen = {}

    async def fake_cascade(prompt, **kwargs):
        seen["prompt"] = prompt

        class R:
            text = "ok"
            provider = "groq"
            model = "m"
            tokens_in = 1
            tokens_out = 1
            cached = False
            truncated = False

        return R()

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", fake_cascade)
    monkeypatch.setattr(ept, "get_active_providers", lambda **k: ["groq"], raising=False)
    import json

    out = json.loads(await ept.cascade_ask("what is alpha", workspace_root=a, use_cache=False))
    assert out.get("used_files") == ["only_in_a.py"], out
    assert "only_in_b" not in seen["prompt"]
