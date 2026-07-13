# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Sprint 2K — 0014_tenant_id_audit_tables + 0014b_backfill_tenant_id.

Run alembic upgrade/downgrade against a temporary sqlite database and
verify:

    1. The column exists on all three RLS-guarded audit tables.
    2. The index exists on each.
    3. Backfill resolves a known license_jti → tenant via the email
       heuristic when no users row is present.
    4. downgrade past 0014 drops the column cleanly (reversible).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
PROJECT_ROOT = ALEMBIC_INI.parent

TABLES = ("customer_audit_entries", "webhook_events", "vault_audit_entries")


def _run_alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ABS_DATABASE_URL"] = db_url
    # Run alembic through the current interpreter so the venv that the
    # test suite is running under (which has sqlmodel + the rest of the
    # backend deps) is used — invoking the "alembic" shim from $PATH
    # would resolve to whichever interpreter installed it, often not the
    # venv. ``python -m alembic`` keeps everything in-process.
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(PROJECT_ROOT),
        check=False,
    )


def _columns(db_path: Path, table: str) -> list[str]:
    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cur.fetchall()]


def _indexes(db_path: Path, table: str) -> list[str]:
    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute(f"PRAGMA index_list({table})")
        return [row[1] for row in cur.fetchall()]


@pytest.fixture()
def fresh_db(tmp_path: Path) -> tuple[Path, str]:
    db_path = tmp_path / "rls_mig.db"
    return db_path, f"sqlite:///{db_path}"


def test_0014_adds_tenant_id_column(fresh_db: tuple[Path, str]) -> None:
    db_path, url = fresh_db
    result = _run_alembic(["upgrade", "0014_tenant_id_audit_tables"], url)
    assert result.returncode == 0, result.stderr

    for table in TABLES:
        cols = _columns(db_path, table)
        assert "tenant_id" in cols, f"{table} missing tenant_id column ({cols})"


def test_0014_adds_tenant_id_index(fresh_db: tuple[Path, str]) -> None:
    db_path, url = fresh_db
    result = _run_alembic(["upgrade", "0014_tenant_id_audit_tables"], url)
    assert result.returncode == 0, result.stderr

    for table in TABLES:
        names = _indexes(db_path, table)
        assert any(
            n.endswith(f"{table}_tenant_id") or n == f"ix_{table}_tenant_id"
            for n in names
        ), f"{table} missing tenant_id index ({names})"


def test_0014b_backfill_resolves_license_email_heuristic(
    fresh_db: tuple[Path, str],
) -> None:
    """Insert a license + customer_audit row, run backfill, observe tenant_id."""

    db_path, url = fresh_db
    result = _run_alembic(["upgrade", "0014_tenant_id_audit_tables"], url)
    assert result.returncode == 0, result.stderr

    import sqlite3
    from datetime import datetime, timezone

    with sqlite3.connect(str(db_path)) as conn:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO licenses (jti, customer_email, customer_id_stripe,
                                  tier, seat_count, issued_at, expires_at,
                                  preferred_lang)
            VALUES ('jti-001', 'admin@demo-acme.com', 'cus_x', 'pro', 1, ?, ?, 'en')
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO customer_audit_entries
                (license_jti, action, ts, tenant_id)
            VALUES ('jti-001', 'login', ?, '_unknown')
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO webhook_events
                (event_id, event_type, received_at, license_jti, tenant_id)
            VALUES ('evt_1', 'invoice.paid', ?, 'jti-001', '_unknown')
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO vault_audit_entries
                (ts, action, actor, hmac, prev_hmac, tenant_id)
            VALUES (?, 'rotate', 'ops@demo-acme.com', 'h', '', '_unknown')
            """,
            (now,),
        )
        conn.commit()

    result = _run_alembic(["upgrade", "0014b_backfill_tenant_id"], url)
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT tenant_id FROM customer_audit_entries WHERE license_jti='jti-001'"
        ).fetchall()
        assert rows == [("demo-acme",)], rows

        rows = conn.execute(
            "SELECT tenant_id FROM webhook_events WHERE event_id='evt_1'"
        ).fetchall()
        assert rows == [("demo-acme",)], rows

        rows = conn.execute(
            "SELECT tenant_id FROM vault_audit_entries WHERE actor='ops@demo-acme.com'"
        ).fetchall()
        assert rows == [("demo-acme",)], rows


def test_0014_downgrade_drops_column(fresh_db: tuple[Path, str]) -> None:
    db_path, url = fresh_db
    up = _run_alembic(["upgrade", "0014_tenant_id_audit_tables"], url)
    assert up.returncode == 0, up.stderr

    # Down past 0014 to 0013.
    down = _run_alembic(["downgrade", "0013_failed_login_attempts"], url)
    assert down.returncode == 0, down.stderr

    for table in TABLES:
        cols = _columns(db_path, table)
        assert "tenant_id" not in cols, (
            f"{table} kept tenant_id after downgrade ({cols})"
        )
