"""Q5.CO1 — Repro state-isolation fixture.

Sprint repro scripts share an SQLite DB and a small set of state files
(`admin_credentials.json`, `setup_state.json`, `users` rows). Running them
in chain after Q3/Q4 magic-link claim mutations breaks older suites.

This helper resets the data layer to a clean baseline so each sprint's
repro can run from a known state. Nothing here is production code — pure
test harness.

Usage:
  python -m tests.util.state_reset clean
  python -m tests.util.state_reset snapshot --sprint=cj
  python -m tests.util.state_reset restore --sprint=cj
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


DATA_DIR = Path("/app/data")
DB_PATH = DATA_DIR / "abs.db"
STATE_FILES = (
    "admin_credentials.json",
    "setup_state.json",
    "tenants_pending.json",
)
SNAPSHOT_DIR = Path("/tmp/abs_state_snapshots")


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def snapshot(sprint_id: str) -> Path:
    """Capture current state to a per-sprint snapshot file."""
    _ensure_dirs()
    payload: dict = {}
    for name in STATE_FILES:
        p = DATA_DIR / name
        if p.exists():
            payload[name] = p.read_text(encoding="utf-8")
    if DB_PATH.exists():
        payload["users_rows"] = _dump_users()
    out = SNAPSHOT_DIR / f"{sprint_id}.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return out


def restore(sprint_id: str) -> bool:
    """Restore previously snapshotted state. No-op if no snapshot exists."""
    snap = SNAPSHOT_DIR / f"{sprint_id}.json"
    if not snap.exists():
        return False
    payload = json.loads(snap.read_text())
    for name in STATE_FILES:
        target = DATA_DIR / name
        if name in payload:
            target.write_text(payload[name], encoding="utf-8")
        elif target.exists():
            target.unlink()
    if "users_rows" in payload:
        _restore_users(payload["users_rows"])
    return True


def _dump_users() -> list[dict]:
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cols = [c[1] for c in conn.execute("PRAGMA table_info(users)").fetchall()]
        if not cols:
            return []
        rows = [
            dict(zip(cols, row))
            for row in conn.execute("SELECT * FROM users").fetchall()
        ]
        conn.close()
        return rows
    except sqlite3.Error as exc:
        logger.debug("dump_users failed: %s", exc)
        return []


def _restore_users(rows: list[dict]) -> None:
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM users")
        if rows:
            cols = list(rows[0].keys())
            placeholders = ",".join("?" for _ in cols)
            col_list = ",".join(cols)
            for r in rows:
                conn.execute(
                    f"INSERT INTO users ({col_list}) VALUES ({placeholders})",
                    [r.get(c) for c in cols],
                )
        conn.commit()
        conn.close()
    except sqlite3.Error as exc:
        logger.debug("restore_users failed: %s", exc)


def clean(*, also_setup_state: bool = False) -> None:
    """Reset auth + telemetry data without dropping setup completion.

    Default leaves `setup_state.json` ALONE: many sprint repros assume the
    `FirstRunMiddleware` is in "setup-completed" mode (so POST routes
    don't get 307'd into the wizard). Pass `also_setup_state=True` only
    when running CJ-style flows that re-exercise the wizard.

    Wipes:
      * admin_credentials.json (so claim/login flows re-bind cleanly)
      * tenants_pending.json (signup mailbox)
      * marketplace_installs.json (per-tenant plugin scope)
      * `users` rows (multi-row login regressions)
      * `feature_usage_log` rows (threshold carry-over)
      * `usage_log` rows (quota seed carry-over)
    """
    _ensure_dirs()
    for name in STATE_FILES:
        if not also_setup_state and name == "setup_state.json":
            continue
        p = DATA_DIR / name
        if p.exists():
            p.unlink()

    # Marketplace installs file lives outside STATE_FILES on purpose so the
    # default snapshot/restore doesn't drag installs back in.
    mp = DATA_DIR / "marketplace_installs.json"
    if mp.exists():
        mp.unlink()

    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        for table in ("users", "feature_usage_log", "usage_log"):
            try:
                conn.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                # Table may not exist on older schemas.
                pass
        conn.commit()
        conn.close()
    except sqlite3.Error as exc:
        logger.debug("clean db tables failed: %s", exc)


def status() -> dict:
    """Snapshot of current state — useful for chain-runner reporting."""
    out: dict = {"timestamp": datetime.now(timezone.utc).isoformat()}
    for name in STATE_FILES:
        p = DATA_DIR / name
        out[name] = "present" if p.exists() else "absent"
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            for table in ("users", "feature_usage_log", "usage_log"):
                try:
                    n = conn.execute(
                        f"SELECT count(*) FROM {table}"
                    ).fetchone()[0]
                    out[f"{table}_rows"] = n
                except sqlite3.OperationalError:
                    out[f"{table}_rows"] = "missing_table"
            conn.close()
        except sqlite3.Error as exc:
            out["db_error"] = str(exc)
    return out


def _cli(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(prog="state_reset")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("clean")
    sub.add_parser("status")
    snap = sub.add_parser("snapshot")
    snap.add_argument("--sprint", required=True)
    rest = sub.add_parser("restore")
    rest.add_argument("--sprint", required=True)
    args = parser.parse_args(list(argv))

    if args.cmd == "clean":
        clean()
        print(json.dumps(status(), indent=2))
        return 0
    if args.cmd == "status":
        print(json.dumps(status(), indent=2))
        return 0
    if args.cmd == "snapshot":
        out = snapshot(args.sprint)
        print(f"snapshot: {out}")
        return 0
    if args.cmd == "restore":
        ok = restore(args.sprint)
        print(f"restore: {'ok' if ok else 'no-snapshot'}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
