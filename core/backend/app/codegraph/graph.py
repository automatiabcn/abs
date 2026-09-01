# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Directed call-graph — blast-radius / callers / callees / related.

Extraction reuses ``app.symbols.parser.parse_directory`` (Python AST call
edges; JS/TS is node-only for now — regex parser has no call edges, so its
blast-radius is honestly partial). On top of that this module builds a
*directed* edge table (caller -> callee) with name resolution
(same-file > workspace, ambiguous stamped ``resolved=0``) and answers
``blast_radius`` via reverse-BFS on ``edges.dst -> src``. Deterministic, no LLM,
no hallucination.

Storage is scoped by ``key`` (the §14 storage abstraction): one SQLite file per
key at ``data_dir/codegraph/<key>.db``. For the local single-user editor the key
is ``workspace_key(root)``; for a hosted multi-tenant server it is the tenant id.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

from app.symbols.parser import parse_directory

_CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx")


def workspace_key(root: str) -> str:
    """Stable per-workspace storage key derived from the real path."""
    real = os.path.realpath(root)
    return "ws_" + hashlib.sha1(real.encode("utf-8")).hexdigest()[:16]


def _db_path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key or "")[:120] or "default"
    p = Path(settings.data_dir) / "codegraph" / f"{safe}.db"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


@contextmanager
def _connect(db: Path):
    conn = sqlite3.connect(str(db), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS symbols (
                id TEXT PRIMARY KEY,
                file TEXT NOT NULL,
                name TEXT NOT NULL,
                leaf TEXT NOT NULL,
                kind TEXT NOT NULL,
                lineno INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_sym_leaf ON symbols(leaf);
            CREATE INDEX IF NOT EXISTS ix_sym_file ON symbols(file);
            CREATE TABLE IF NOT EXISTS edges (
                src_id TEXT NOT NULL,
                dst_id TEXT NOT NULL,
                dst_name TEXT NOT NULL,
                resolved INTEGER NOT NULL,
                UNIQUE(src_id, dst_id, dst_name)
            );
            CREATE INDEX IF NOT EXISTS ix_edge_dst ON edges(dst_id);
            CREATE INDEX IF NOT EXISTS ix_edge_src ON edges(src_id);
            """
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def _leaf(name: str) -> str:
    return name.split(".")[-1]


def build(root: str, *, key: str = "default", incremental: bool = True) -> Dict[str, Any]:
    """(Re)build the directed graph for a workspace root.

    ``incremental`` is reserved; the current implementation is a full,
    deterministic rebuild of this key's graph (correctness first — per-file mtime
    incrementality is a later optimisation).
    """
    root = os.path.realpath(root)
    # Confined to the workspace itself. The process-wide allowed roots are the
    # server's own trees; a customer's project is never among them, and the
    # walk used to come back empty for every real project — 0 symbols, no
    # error, blast radius forever "not indexed" (audit, 2026-08-18). The
    # caller has vetted `root` (problem_with_root / registered roots); here it
    # is the boundary, and a symlink leading out of it is still refused.
    try:
        parsed = parse_directory(Path(root), roots=[Path(root)], strict=True)
    except PermissionError as exc:
        # Say so. An empty graph written here would answer every later
        # blast-radius question with confident nothing.
        return {
            "root": root,
            "symbols": 0,
            "edges": 0,
            "new_edges": 0,
            "error": f"root not readable: {exc}",
        }
    syms = [s for s in parsed if s.kind in ("function", "class")]

    by_leaf: Dict[str, List[tuple]] = {}
    sym_rows = []
    for s in syms:
        leaf = _leaf(s.name)
        sid = f"{s.file}::{s.name}"
        sym_rows.append((sid, s.file, s.name, leaf, s.kind, s.lineno))
        by_leaf.setdefault(leaf, []).append((sid, s.file))

    n_edge = 0
    with _connect(_db_path(key)) as c:
        c.execute("DELETE FROM edges")
        c.execute("DELETE FROM symbols")
        if sym_rows:
            c.executemany(
                "INSERT OR REPLACE INTO symbols VALUES (?, ?, ?, ?, ?, ?)", sym_rows
            )
        for s in syms:
            if s.kind != "function":
                continue
            src_id = f"{s.file}::{s.name}"
            for callee in s.edges_out:
                cands = by_leaf.get(_leaf(callee))
                if not cands:
                    continue  # external / builtin — not a node
                same_file = [x for x in cands if x[1] == s.file]
                pick = same_file or cands
                # Resolved when unambiguous (same-file hit, or a single candidate).
                resolved = 1 if (same_file or len(cands) == 1) else 0
                for dst_id, _ in pick[:3]:  # at most 3 guesses when ambiguous
                    if dst_id == src_id:
                        continue
                    try:
                        c.execute(
                            "INSERT OR IGNORE INTO edges VALUES (?, ?, ?, ?)",
                            (src_id, dst_id, callee, resolved),
                        )
                        n_edge += 1
                    except sqlite3.Error:
                        pass
        total = c.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        total_e = c.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    return {
        "root": root,
        "symbols": total,
        "edges": total_e,
        "new_edges": n_edge,
    }


def tenant_key(tenant: str, root: str) -> str:
    """The storage key for one tenant's one project — hashed, so a customer's
    directory layout never ends up in logs or on disk. The MCP tool layer
    (`codegraph_tools._key_for`) and the editor agent both use this one."""
    import hashlib

    try:
        resolved = os.path.realpath(root)
    except OSError:
        resolved = root
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:12]
    return f"{tenant}:{digest}"


def blast_radius(target: str, *, key: str = "default", max_hops: int = 3) -> Dict[str, Any]:
    """Symbols affected if ``target`` changes = its transitive CALLERS.

    ``target`` is a symbol name or a file path. Reverse-BFS on ``dst -> src``.
    """
    with _connect(_db_path(key)) as c:
        if os.sep in target or target.endswith(_CODE_SUFFIXES):
            seeds = [r[0] for r in c.execute(
                "SELECT id FROM symbols WHERE file = ?", (target,)
            )]
            if not seeds:
                seeds = [r[0] for r in c.execute(
                    "SELECT id FROM symbols WHERE file LIKE ?", (f"%{target}%",)
                )]
        else:
            seeds = [r[0] for r in c.execute(
                "SELECT id FROM symbols WHERE leaf = ? OR name = ?", (target, target)
            )]

        if not seeds:
            # "No callers" and "never indexed" are different answers, and this
            # returned the first for both. A developer asking what breaks if
            # they change a function, on a project the graph has never read,
            # was told nothing breaks — a factual claim about their code, made
            # without reading it. Somebody could delete a live function on the
            # strength of it. Found 2026-08-03 while walking the project rule.
            total = c.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            if not total:
                return {
                    "target": target,
                    "found": False,
                    "indexed": False,
                    "total_affected": 0,
                    "affected_files": [],
                    "layers": [],
                    "note": (
                        "This project has not been indexed, so nothing is known "
                        "about its callers — this is not the same as having none. "
                        "Run code_graph_build on the project first."
                    ),
                }
            return {
                "target": target,
                "found": False,
                "indexed": True,
                "total_affected": 0,
                "affected_files": [],
                "layers": [],
            }

        visited = set(seeds)
        frontier = set(seeds)
        layers: List[Dict[str, Any]] = []
        for hop in range(max(1, max_hops)):
            nxt = set()
            for sid in frontier:
                for (caller,) in c.execute(
                    "SELECT src_id FROM edges WHERE dst_id = ?", (sid,)
                ):
                    if caller not in visited:
                        nxt.add(caller)
            if not nxt:
                break
            visited |= nxt
            qmarks = ",".join("?" * len(nxt))
            rows = [
                {"symbol": r["name"], "file": r["file"], "kind": r["kind"]}
                for r in c.execute(
                    f"SELECT name, file, kind FROM symbols WHERE id IN ({qmarks})",
                    tuple(nxt),
                )
            ]
            layers.append({"hop": hop + 1, "count": len(rows), "symbols": rows})
            frontier = nxt

        affected_files = sorted({r["file"] for L in layers for r in L["symbols"]})
        return {
            "target": target,
            "found": True,
            # Reported on every path, so a caller can test the field instead of
            # treating "absent" as "true" — an implicit contract like that
            # breaks the first time a branch forgets to set it.
            "indexed": True,
            "seed_symbols": len(seeds),
            "total_affected": sum(L["count"] for L in layers),
            "affected_files": affected_files,
            "layers": layers,
        }


def callers(name: str, *, key: str = "default") -> List[Dict[str, Any]]:
    """Direct callers of ``name``."""
    with _connect(_db_path(key)) as c:
        return [
            {"symbol": r["name"], "file": r["file"], "resolved": bool(r["resolved"])}
            for r in c.execute(
                "SELECT s.name AS name, s.file AS file, e.resolved AS resolved "
                "FROM edges e JOIN symbols s ON e.src_id = s.id "
                "WHERE e.dst_id IN (SELECT id FROM symbols WHERE leaf = ? OR name = ?)",
                (name, name),
            )
        ]


def callees(name: str, *, key: str = "default") -> List[Dict[str, Any]]:
    """Symbols that ``name`` calls."""
    with _connect(_db_path(key)) as c:
        return [
            {"name": r["dst_name"], "resolved": bool(r["resolved"])}
            for r in c.execute(
                "SELECT e.dst_name AS dst_name, e.resolved AS resolved FROM edges e "
                "WHERE e.src_id IN (SELECT id FROM symbols WHERE leaf = ? OR name = ?)",
                (name, name),
            )
        ]


def graph_related(name: str, *, key: str = "default", depth: int = 1) -> Dict[str, Any]:
    """Undirected neighbourhood within ``depth`` hops (callers + callees)."""
    with _connect(_db_path(key)) as c:
        seeds = [r[0] for r in c.execute(
            "SELECT id FROM symbols WHERE leaf = ? OR name = ?", (name, name)
        )]
        if not seeds:
            return {"name": name, "found": False, "related": []}
        visited = set(seeds)
        frontier = set(seeds)
        for _ in range(max(1, depth)):
            nxt = set()
            for sid in frontier:
                for (other,) in c.execute(
                    "SELECT dst_id FROM edges WHERE src_id = ? "
                    "UNION SELECT src_id FROM edges WHERE dst_id = ?",
                    (sid, sid),
                ):
                    if other not in visited:
                        nxt.add(other)
            visited |= nxt
            frontier = nxt
            if not nxt:
                break
        ids = visited - set(seeds)
        related: List[Dict[str, Any]] = []
        if ids:
            qmarks = ",".join("?" * len(ids))
            related = [
                {"symbol": r["name"], "file": r["file"]}
                for r in c.execute(
                    f"SELECT name, file FROM symbols WHERE id IN ({qmarks})", tuple(ids)
                )
            ]
        return {"name": name, "found": True, "related": related}


def stats(*, key: str = "default") -> Dict[str, Any]:
    p = _db_path(key)
    with _connect(p) as c:
        s = c.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        e = c.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        er = c.execute("SELECT COUNT(*) FROM edges WHERE resolved = 1").fetchone()[0]
    return {
        "symbols": s,
        "edges": e,
        "resolved_edges": er,
        "resolved_pct": round(100 * er / max(e, 1), 1),
        "db": str(p),
    }


def count_symbols(*, key: str = "default") -> int:
    """How many symbols this project's graph holds.

    "Has this project been read?" was answered from the standalone symbols.db
    until 2026-08-04, and the editor's index command never writes there — it
    calls code_graph_build, which writes here. So the answer was always "no",
    the editor offered to index on every launch, and the offer never took
    effect as far as the check could see. Found by walking the editor's own
    sequence over the wire.
    """
    try:
        with _connect(_db_path(key)) as c:
            row = c.execute("SELECT COUNT(*) FROM symbols").fetchone()
        return int(row[0] if row else 0)
    except Exception:  # noqa: BLE001 — an unreadable graph is an empty one
        return 0


def search_symbols(
    name_substr: str,
    *,
    key: str = "default",
    kind: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Symbols in this project's graph, matching a substring.

    Served from the graph rather than the global symbols.db because the graph
    is already keyed per project: scoping comes for free, where the global
    store needed a path prefix and only worked if something had filled it.
    """
    sql = "SELECT name, kind, file, lineno FROM symbols WHERE (name LIKE ? OR leaf LIKE ?)"
    params: List[Any] = [f"%{name_substr}%", f"%{name_substr}%"]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY name LIMIT ?"
    params.append(limit)
    try:
        with _connect(_db_path(key)) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        return []
