# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Workflow durability — SQLite checkpoints.

Multi-step pipelines record each step, so a run interrupted halfway can be
picked up from its last successful step with `resume(trace_id)`.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings


def _db_path() -> Path:
    p = Path(settings.data_dir) / "workflow_state.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workflows (
            id            TEXT PRIMARY KEY,
            type          TEXT NOT NULL,
            prompt_hash   TEXT NOT NULL,
            started_at    REAL NOT NULL,
            finished_at   REAL,
            status        TEXT NOT NULL DEFAULT 'running'
        );
        CREATE TABLE IF NOT EXISTS steps (
            workflow_id   TEXT NOT NULL,
            step_idx      INTEGER NOT NULL,
            name          TEXT NOT NULL,
            status        TEXT NOT NULL,
            result_json   TEXT,
            started_at    REAL NOT NULL,
            finished_at   REAL,
            PRIMARY KEY (workflow_id, step_idx),
            FOREIGN KEY (workflow_id) REFERENCES workflows(id)
        );
        CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);
        CREATE INDEX IF NOT EXISTS idx_workflows_type ON workflows(type);
        """
    )


@contextmanager
def _connect():
    conn = sqlite3.connect(str(_db_path()), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        _init_db(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _make_trace_id() -> str:
    """Short unique trace id — the first 16 hex chars of a uuid4."""
    return uuid.uuid4().hex[:16]


def _prompt_hash(prompt: str) -> str:
    import hashlib

    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def start_workflow(wf_type: str, prompt: str) -> str:
    """Start a workflow and return its trace id."""
    trace_id = _make_trace_id()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO workflows (id, type, prompt_hash, started_at, status) "
            "VALUES (?, ?, ?, ?, 'running')",
            (trace_id, wf_type, _prompt_hash(prompt or ""), time.time()),
        )
    return trace_id


def record_step(
    trace_id: str,
    step_name: str,
    status: str = "ok",
    result: Optional[Dict[str, Any]] = None,
) -> int:
    """Append a step record to a workflow and return its step index."""
    now = time.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(step_idx), -1) AS last_idx FROM steps WHERE workflow_id = ?",
            (trace_id,),
        ).fetchone()
        last = row["last_idx"]
        next_idx = (last if last is not None else -1) + 1
        conn.execute(
            "INSERT INTO steps (workflow_id, step_idx, name, status, result_json, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                trace_id,
                next_idx,
                step_name,
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                now,
                now,
            ),
        )
    return next_idx


def finish_workflow(trace_id: str, status: str = "ok") -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE workflows SET finished_at = ?, status = ? WHERE id = ?",
            (time.time(), status, trace_id),
        )


def get_workflow(trace_id: str) -> Dict[str, Any]:
    with _connect() as conn:
        wf = conn.execute("SELECT * FROM workflows WHERE id = ?", (trace_id,)).fetchone()
        if not wf:
            return {}
        steps = conn.execute(
            "SELECT * FROM steps WHERE workflow_id = ? ORDER BY step_idx",
            (trace_id,),
        ).fetchall()
        return {
            "id": wf["id"],
            "type": wf["type"],
            "prompt_hash": wf["prompt_hash"],
            "started_at": wf["started_at"],
            "finished_at": wf["finished_at"],
            "status": wf["status"],
            "steps": [
                {
                    "step_idx": s["step_idx"],
                    "name": s["name"],
                    "status": s["status"],
                    "result": json.loads(s["result_json"]) if s["result_json"] else None,
                    "started_at": s["started_at"],
                    "finished_at": s["finished_at"],
                }
                for s in steps
            ],
        }


def resume(trace_id: str) -> Dict[str, Any]:
    """Return the state needed to continue from the last successful step."""
    wf = get_workflow(trace_id)
    if not wf:
        return {"error": f"workflow yok: {trace_id}"}
    last_ok = None
    for s in wf["steps"]:
        if s["status"] == "ok":
            last_ok = s
    return {
        "workflow_id": trace_id,
        "type": wf["type"],
        "status": wf["status"],
        "total_steps": len(wf["steps"]),
        "last_ok_step": last_ok,
        "remaining": "Resume point is pipeline-defined; the caller interprets it",
    }


def list_workflows(
    limit: int = 20,
    status: Optional[str] = None,
    wf_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM workflows WHERE 1=1"
    params: List[Any] = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if wf_type:
        sql += " AND type = ?"
        params.append(wf_type)
    sql += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {
            "id": r["id"],
            "type": r["type"],
            "started_at": r["started_at"],
            "finished_at": r["finished_at"],
            "status": r["status"],
        }
        for r in rows
    ]


def cleanup_old(days: int = 30) -> int:
    """Delete finished workflows older than `days`, and their steps. Returns the
    number of workflows removed. Unfinished workflows are never touched."""
    cutoff = time.time() - days * 86400
    with _connect() as conn:
        ids_rows = conn.execute(
            "SELECT id FROM workflows WHERE finished_at IS NOT NULL AND finished_at < ?",
            (cutoff,),
        ).fetchall()
        ids = [r["id"] for r in ids_rows]
        if not ids:
            return 0
        # T-Q01: f-string only injects server-generated `?,?,?` placeholders
        # (one per id, length-bounded by the SELECT above), never user input.
        # Actual id values bind via the `ids` argument as parameters.
        placeholders = ",".join("?" for _ in ids)
        conn.execute(  # nosec B608 — parametrized via `ids`; placeholders are server-generated `?` chars
            f"DELETE FROM steps WHERE workflow_id IN ({placeholders})", ids
        )
        conn.execute(  # nosec B608 — see comment above
            f"DELETE FROM workflows WHERE id IN ({placeholders})", ids
        )
        return len(ids)


def stats() -> Dict[str, Any]:
    """Summary counters over the workflow table, for dashboards."""
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM workflows").fetchone()["c"]
        by_status = {
            r["status"]: r["c"]
            for r in conn.execute(
                "SELECT status, COUNT(*) c FROM workflows GROUP BY status"
            )
        }
        recent_wf = conn.execute(
            "SELECT id, type, status, started_at FROM workflows "
            "ORDER BY started_at DESC LIMIT 5"
        ).fetchall()
    db_size_kb = round(_db_path().stat().st_size / 1024, 1) if _db_path().exists() else 0.0
    return {
        "total_workflows": total,
        "by_status": by_status,
        "recent": [
            {
                "id": r["id"],
                "type": r["type"],
                "status": r["status"],
                "started_at": r["started_at"],
            }
            for r in recent_wf
        ],
        "db_size_kb": db_size_kb,
    }
