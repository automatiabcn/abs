# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Symbol SQLite store (symbols + edges)."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

from .parser import Symbol


def _db_path() -> Path:
    p = Path(settings.data_dir) / "symbols.db"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


@contextmanager
def _connect():
    conn = sqlite3.connect(str(_db_path()), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                file TEXT NOT NULL,
                lineno INTEGER NOT NULL,
                parent TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
            CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
            CREATE TABLE IF NOT EXISTS edges (
                from_sym TEXT NOT NULL,
                to_sym TEXT NOT NULL,
                file TEXT NOT NULL,
                UNIQUE(from_sym, to_sym, file)
            );
            CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_sym);
            CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_sym);
            """
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def reset() -> None:
    p = _db_path()
    if p.is_file():
        try:
            p.unlink()
        except OSError:
            pass


def bulk_insert(symbols: List[Symbol]) -> int:
    if not symbols:
        return 0
    with _connect() as conn:
        cur = conn.executemany(
            "INSERT INTO symbols (name, kind, file, lineno, parent) "
            "VALUES (?, ?, ?, ?, ?)",
            [(s.name, s.kind, s.file, s.lineno, s.parent) for s in symbols],
        )
        edge_rows = [(s.name, e, s.file) for s in symbols for e in s.edges_out]
        if edge_rows:
            conn.executemany(
                "INSERT OR IGNORE INTO edges (from_sym, to_sym, file) VALUES (?, ?, ?)",
                edge_rows,
            )
        return cur.rowcount or 0


def search(
    name_substr: str,
    limit: int = 20,
    kind: Optional[str] = None,
    under: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Symbols matching a substring, optionally only those under a directory.

    `under` exists because this searched everything the server had ever
    indexed. A developer with two projects open at different times got the
    other one's symbols in their results, with nothing to say which repository
    a hit came from. Paths are stored absolute, so a prefix is enough and no
    schema change is needed.
    """
    sql = "SELECT name, kind, file, lineno FROM symbols WHERE name LIKE ?"
    params: List[Any] = [f"%{name_substr}%"]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if under:
        # Resolved on both sides, or the filter silently matches nothing.
        #
        # The workspace is stored with realpath() and the indexer records the
        # path it was handed. On macOS /var is a symlink to /private/var, so
        # scoping a project under /var/... against symbols recorded as
        # /private/var/... returned zero rows — no error, no results, and
        # nothing to suggest the filter rather than the repository was empty.
        try:
            root = os.path.realpath(under).rstrip("/") + "/"
        except OSError:
            root = under.rstrip("/") + "/"
        sql += " AND file LIKE ?"
        params.append(f"{root}%")
    sql += " ORDER BY name LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def neighbors(name: str, depth: int = 1) -> Dict[str, Any]:
    """Neighbours within N hops. Direction is ignored — inbound and outbound edges are merged."""
    with _connect() as conn:
        sym = conn.execute(
            "SELECT * FROM symbols WHERE name = ? LIMIT 1", (name,)
        ).fetchone()
        if not sym:
            return {"status": "not_found", "name": name}
        visited = {name}
        edges_collected: List[Dict[str, Any]] = []
        frontier = {name}
        for _ in range(max(1, int(depth))):
            new_frontier: set = set()
            for node in frontier:
                rows = conn.execute(
                    "SELECT to_sym AS other, file FROM edges WHERE from_sym = ? "
                    "UNION "
                    "SELECT from_sym AS other, file FROM edges WHERE to_sym = ?",
                    (node, node),
                ).fetchall()
                for r in rows:
                    other = r["other"]
                    edges_collected.append(
                        {"from": node, "to": other, "file": r["file"]}
                    )
                    if other not in visited:
                        visited.add(other)
                        new_frontier.add(other)
            frontier = new_frontier
        return {
            "status": "ok",
            "root": dict(sym),
            "depth": depth,
            "neighbors": [{"name": n} for n in sorted(visited - {name})],
            "edges": edges_collected[:200],
            "total_visited": len(visited),
        }


def stats() -> Dict[str, Any]:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM symbols").fetchone()["c"]
        edges = conn.execute("SELECT COUNT(*) AS c FROM edges").fetchone()["c"]
        by_kind = {
            r["kind"]: r["c"]
            for r in conn.execute("SELECT kind, COUNT(*) c FROM symbols GROUP BY kind")
        }
    return {"total_symbols": total, "total_edges": edges, "by_kind": by_kind}


def count_under(root: str) -> int:
    """How many symbols are recorded under a directory.

    Used to tell "this project has not been indexed" apart from "this project
    has no such symbol". The two returned identical empty results until
    2026-08-03, and only one of them is an answer about the code.
    """
    try:
        base = os.path.realpath(root).rstrip("/") + "/"
    except OSError:
        base = root.rstrip("/") + "/"
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM symbols WHERE file LIKE ?", (f"{base}%",)
        ).fetchone()
    return int(row[0] if row else 0)
