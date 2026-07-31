# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Tasks — the companion that closes the meeting → task → code chain.

A task is a commitment with a trail: it says where it came from (typed by
hand, lifted from a meeting's action items, left over from a Composer run)
and, when it points at code, which file it is about. That trail is the whole
point — a bare todo list is what every other tool already has.

Storage mirrors the notes companion: one SQLite file per caller key under
``data_dir``, no ORM, no server dependency. Same reasoning too: the companion
must work in the self-host/air-gap tier, so it depends on nothing that is not
already on the machine.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings

_STATUSES = ("open", "done")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db_path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key or "")[:120] or "default"
    p = Path(settings.data_dir) / "tasks" / f"{safe}.db"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


@contextmanager
def _connect(key: str):
    conn = sqlite3.connect(str(_db_path(key)), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                body       TEXT DEFAULT '',
                status     TEXT DEFAULT 'open',
                source     TEXT DEFAULT 'manual',
                file       TEXT DEFAULT '',
                project    TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT,
                done_at    TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks(status)")
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row(r: sqlite3.Row) -> Dict[str, Any]:
    return dict(r)


def add(
    title: str,
    *,
    key: str = "default",
    body: str = "",
    source: str = "manual",
    file: str = "",
    project: str = "",
) -> Dict[str, Any]:
    """Create a task. ``source`` records where it came from — 'manual',
    'meeting:<id>', 'composer:<run_id>' — and is never invented."""
    title = (title or "").strip()
    if not title:
        return {"ok": False, "error": "a task needs a title"}
    task_id = uuid.uuid4().hex[:12]
    now = _now()
    with _connect(key) as c:
        c.execute(
            "INSERT INTO tasks (id, title, body, status, source, file, project,"
            " created_at, updated_at) VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?)",
            (task_id, title[:300], (body or "")[:4000], (source or "manual")[:120],
             (file or "")[:400], (project or "")[:120], now, now),
        )
    return {"ok": True, "id": task_id, "title": title[:300], "status": "open"}


def list_tasks(
    *, key: str = "default", status: str = "open", limit: int = 100
) -> List[Dict[str, Any]]:
    """Tasks, open ones first and newest within a status. ``status`` may be
    'open', 'done' or 'all'."""
    q = "SELECT * FROM tasks"
    args: tuple = ()
    if status in _STATUSES:
        q += " WHERE status = ?"
        args = (status,)
    q += " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, created_at DESC LIMIT ?"
    with _connect(key) as c:
        rows = c.execute(q, args + (int(limit),)).fetchall()
    return [_row(r) for r in rows]


def set_status(task_id: str, status: str, *, key: str = "default") -> Dict[str, Any]:
    """Mark a task open or done. Says so when the task does not exist —
    a silent success on a missing id would read as work completed."""
    if status not in _STATUSES:
        return {"ok": False, "error": f"status must be one of {_STATUSES}"}
    now = _now()
    with _connect(key) as c:
        cur = c.execute(
            "UPDATE tasks SET status = ?, updated_at = ?, done_at = ? WHERE id = ?",
            (status, now, now if status == "done" else None, task_id),
        )
        if cur.rowcount == 0:
            return {"ok": False, "error": "task_not_found"}
    return {"ok": True, "id": task_id, "status": status}


def delete(task_id: str, *, key: str = "default") -> bool:
    with _connect(key) as c:
        cur = c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cur.rowcount > 0


def stats(*, key: str = "default") -> Dict[str, Any]:
    with _connect(key) as c:
        rows = c.execute(
            "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
        ).fetchall()
    by = {r["status"]: r["n"] for r in rows}
    return {"open": by.get("open", 0), "done": by.get("done", 0)}
