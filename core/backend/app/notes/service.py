# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Notes — a small Notion-like notes/doc store for the editor's companion panel.

CRUD + lexical search over per-key SQLite (``data_dir/notes/<key>.db``). The key
is the §14 storage scope: the local workspace for the single-user editor, the
tenant id for a hosted server. Self-contained — no RAG/meeting coupling (an
optional RAG-index hook can be added later).
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db_path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key or "")[:120] or "default"
    p = Path(settings.data_dir) / "notes" / f"{safe}.db"
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
            CREATE TABLE IF NOT EXISTS notes (
                id         TEXT PRIMARY KEY,
                title      TEXT,
                body       TEXT,
                project    TEXT,
                tags       TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS ix_notes_proj ON notes(project)")
        yield conn
        conn.commit()
    finally:
        conn.close()


def _tokens(text: str) -> set:
    return {t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) > 1}


def save(
    title: str,
    body: str,
    *,
    key: str = "default",
    note_id: Optional[str] = None,
    project: Optional[str] = None,
    tags: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update a note. Returns the note's id + timestamps."""
    title = (title or "").strip() or "Untitled note"
    body = body or ""
    now = _now()
    with _connect(key) as c:
        existing = None
        if note_id:
            existing = c.execute(
                "SELECT created_at FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
        if note_id and existing:
            c.execute(
                "UPDATE notes SET title=?, body=?, project=?, tags=?, updated_at=? WHERE id=?",
                (title, body, project, tags or "", now, note_id),
            )
            nid = note_id
            created = existing["created_at"]
        else:
            nid = note_id or ("n-" + uuid.uuid4().hex[:12])
            c.execute(
                "INSERT INTO notes (id, title, body, project, tags, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nid, title, body, project, tags or "", now, now),
            )
            created = now
    return {"id": nid, "title": title, "project": project, "created_at": created, "updated_at": now}


def get(note_id: str, *, key: str = "default") -> Optional[Dict[str, Any]]:
    with _connect(key) as c:
        r = c.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return dict(r) if r else None


def list_notes(*, key: str = "default", limit: int = 100) -> List[Dict[str, Any]]:
    with _connect(key) as c:
        rows = c.execute(
            "SELECT id, title, project, tags, created_at, updated_at, "
            "substr(body, 1, 160) AS preview FROM notes "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def search(query: str, *, key: str = "default", top_k: int = 10) -> List[Dict[str, Any]]:
    q = _tokens(query)
    if not q:
        return []
    with _connect(key) as c:
        rows = c.execute("SELECT id, title, body, project FROM notes").fetchall()
    scored = []
    for r in rows:
        overlap = len(_tokens(f"{r['title']} {r['body']}") & q)
        if overlap:
            scored.append(
                {
                    "score": overlap,
                    "id": r["id"],
                    "title": r["title"],
                    "project": r["project"],
                    "preview": (r["body"] or "")[:160],
                }
            )
    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def delete(note_id: str, *, key: str = "default") -> bool:
    with _connect(key) as c:
        cur = c.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        return cur.rowcount > 0


def stats(*, key: str = "default") -> Dict[str, Any]:
    with _connect(key) as c:
        n = c.execute("SELECT COUNT(*) AS n FROM notes").fetchone()["n"]
    return {"notes": n, "db": str(_db_path(key))}
