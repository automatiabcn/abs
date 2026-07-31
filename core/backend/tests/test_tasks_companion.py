# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Tasks companion — the meeting → task → code chain.

A task's trail (source, file) is the feature; these tests pin the trail and
the honesty rules: a missing id is an error, never a silent success, and one
caller's tasks are invisible to another.
"""

from __future__ import annotations

import asyncio

import pytest

from app.tasks_companion import service as tasks


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.settings, "data_dir", str(tmp_path))


def test_a_task_keeps_its_trail():
    r = tasks.add(
        "wire the retry",
        key="t1",
        source="meeting:42",
        file="src/retry.py",
        body="from Monday's standup",
    )
    assert r["ok"] is True
    row = tasks.list_tasks(key="t1")[0]
    assert row["source"] == "meeting:42"
    assert row["file"] == "src/retry.py"
    assert row["status"] == "open"


def test_done_moves_it_out_of_the_open_list_with_a_timestamp():
    tid = tasks.add("ship it", key="t2")["id"]
    assert tasks.set_status(tid, "done", key="t2")["ok"] is True
    assert tasks.list_tasks(key="t2", status="open") == []
    done = tasks.list_tasks(key="t2", status="done")[0]
    assert done["done_at"], "done must say when"
    # Reopening clears the completion time — it is open again, not half-done.
    tasks.set_status(tid, "open", key="t2")
    assert tasks.list_tasks(key="t2", status="open")[0]["done_at"] is None


def test_a_missing_id_is_an_error_not_a_silent_success():
    out = tasks.set_status("nope", "done", key="t3")
    assert out["ok"] is False
    assert out["error"] == "task_not_found"


def test_a_blank_title_is_refused():
    assert tasks.add("   ", key="t4")["ok"] is False


def test_callers_do_not_see_each_others_tasks():
    tasks.add("mine", key="tenant-a")
    assert tasks.list_tasks(key="tenant-b") == []


def test_open_sorts_before_done_in_the_all_view():
    a = tasks.add("first", key="t5")["id"]
    tasks.add("second", key="t5")
    tasks.set_status(a, "done", key="t5")
    rows = tasks.list_tasks(key="t5", status="all")
    assert rows[0]["status"] == "open"
    assert rows[-1]["status"] == "done"


def test_the_mcp_tools_are_registered():
    from app.mcp.server import mcp_server

    names = {t.name for t in asyncio.run(mcp_server.list_tools())}
    assert {"task_add", "task_list", "task_done", "task_delete"} <= names
