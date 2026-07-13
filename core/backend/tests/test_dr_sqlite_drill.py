"""DR drill — backup_sqlite.sh → restore_sqlite.sh round-trips real data.

The default ABS deployment runs on SQLite; before this round it had no
supported backup path (the dr-runbook + scripts were Postgres-only). These
tests exercise the new scripts end-to-end against a throwaway DB and assert
the data survives a backup → wipe → restore cycle with integrity intact.
"""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKUP_SH = REPO_ROOT / "scripts" / "dr" / "backup_sqlite.sh"
RESTORE_SH = REPO_ROOT / "scripts" / "dr" / "restore_sqlite.sh"

pytestmark = pytest.mark.skipif(
    not BACKUP_SH.exists() or not RESTORE_SH.exists(),
    reason="DR sqlite scripts not present",
)


def _seed_db(path: Path, rows: int) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE tenants (id INTEGER PRIMARY KEY, slug TEXT)")
    conn.executemany(
        "INSERT INTO tenants (slug) VALUES (?)",
        [(f"acme-{i}",) for i in range(rows)],
    )
    conn.commit()
    conn.close()


def _run(
    script: Path, *args: str, env_extra: dict | None = None
) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_backup_restore_roundtrip_preserves_rows(tmp_path: Path):
    data_dir = tmp_path / "data"
    backup_dir = tmp_path / "backups"
    data_dir.mkdir()
    _seed_db(data_dir / "abs.db", rows=7)

    # 1. Back up.
    b = _run(
        BACKUP_SH,
        env_extra={"ABS_DATA_DIR": str(data_dir), "ABS_BACKUP_DIR": str(backup_dir)},
    )
    assert b.returncode == 0, b.stderr
    bundles = list(backup_dir.glob("abs-sqlite-*.tar.gz"))
    assert len(bundles) == 1, f"expected one bundle, got {bundles}"

    # 2. Simulate disaster: wipe the data dir.
    (data_dir / "abs.db").unlink()

    # 3. Restore into the (now empty) data dir.
    r = _run(
        RESTORE_SH,
        str(bundles[0]),
        env_extra={"ABS_DATA_DIR": str(data_dir)},
    )
    assert r.returncode == 0, r.stderr

    # 4. Data survived + DB is consistent.
    restored = data_dir / "abs.db"
    assert restored.exists()
    conn = sqlite3.connect(restored)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 7
    conn.close()


def test_backup_fails_loudly_when_db_missing(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    b = _run(BACKUP_SH, env_extra={"ABS_DATA_DIR": str(data_dir)})
    assert b.returncode != 0
    assert "database not found" in (b.stderr + b.stdout).lower()


def test_restore_keeps_pre_restore_copy(tmp_path: Path):
    data_dir = tmp_path / "data"
    backup_dir = tmp_path / "backups"
    data_dir.mkdir()
    _seed_db(data_dir / "abs.db", rows=3)
    _run(
        BACKUP_SH,
        env_extra={"ABS_DATA_DIR": str(data_dir), "ABS_BACKUP_DIR": str(backup_dir)},
    )
    bundle = next(backup_dir.glob("abs-sqlite-*.tar.gz"))

    # Mutate the live DB so we can prove the pre-restore copy captured it.
    conn = sqlite3.connect(data_dir / "abs.db")
    conn.execute("INSERT INTO tenants (slug) VALUES ('about-to-be-rolled-back')")
    conn.commit()
    conn.close()

    r = _run(RESTORE_SH, str(bundle), env_extra={"ABS_DATA_DIR": str(data_dir)})
    assert r.returncode == 0, r.stderr

    pre = list(data_dir.glob("abs.db.pre-restore-*"))
    assert len(pre) == 1, "restore must snapshot the current DB before overwriting"
    conn = sqlite3.connect(pre[0])
    assert conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 4
    conn.close()
