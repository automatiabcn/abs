"""Workflow durability — start/record/finish/resume/cleanup."""

from __future__ import annotations

import time

import pytest

from app.config import settings
from app.workflow import (
    cleanup_old,
    finish_workflow,
    get_workflow,
    list_workflows,
    record_step,
    resume,
    start_workflow,
)


@pytest.fixture(autouse=True)
def _tmp_data(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))


def test_start_record_finish_get_workflow():
    tid = start_workflow("pipeline-code", "fibonacci yaz")
    assert len(tid) == 16
    record_step(tid, "generate", "ok", {"model": "groq", "elapsed": 1.2})
    record_step(tid, "verify", "ok", {"model": "ollama"})
    finish_workflow(tid, "ok")

    wf = get_workflow(tid)
    assert wf["status"] == "ok"
    assert wf["finished_at"] is not None
    assert len(wf["steps"]) == 2
    assert wf["steps"][0]["name"] == "generate"
    assert wf["steps"][0]["result"]["model"] == "groq"


def test_resume_returns_last_ok_step():
    tid = start_workflow("pipeline-tr", "react ne")
    record_step(tid, "draft", "ok", {"text": "Reactive UI lib"})
    record_step(tid, "review", "fail", {"err": "ollama down"})

    r = resume(tid)
    assert r["workflow_id"] == tid
    assert r["last_ok_step"]["name"] == "draft"
    assert r["total_steps"] == 2


def test_cleanup_old_removes_old_workflows():
    tid = start_workflow("test-old", "x")
    finish_workflow(tid, "ok")

    # Manuel olarak finished_at'i 60 gün geriye it
    import sqlite3

    from app.workflow.state import _db_path

    conn = sqlite3.connect(str(_db_path()))
    conn.execute(
        "UPDATE workflows SET finished_at = ? WHERE id = ?",
        (time.time() - 60 * 86400, tid),
    )
    conn.commit()
    conn.close()

    deleted = cleanup_old(days=30)
    assert deleted == 1
    assert get_workflow(tid) == {}


def test_list_workflows_status_filter():
    a = start_workflow("p1", "a")
    b = start_workflow("p2", "b")
    finish_workflow(a, "ok")
    # b hâlâ running
    running = list_workflows(status="running")
    assert any(w["id"] == b for w in running)
    assert all(w["status"] == "running" for w in running)
    ok_list = list_workflows(status="ok")
    assert any(w["id"] == a for w in ok_list)
