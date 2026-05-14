# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Sprint 2K — RLS enforcement on the 3 audit tables.

The default lane runs against SQLite, which has no RLS engine; these
tests therefore carry the ``postgres_only`` marker so they only run on
the new CI postgres matrix lane (FAZ F). Locally the suite is skipped
when ``ABS_TEST_POSTGRES_URL`` is unset.

The contract under test:

    1. Tenant A writes a row → Tenant B's session sees zero rows.
    2. Tenant A writes a row → Tenant A's session sees one row.
    3. No GUC set → policy denies SELECT (force RLS).
    4. Wrong GUC → SELECT returns zero rows.
    5. Downgrade past 0015 → policy disappears, both tenants see all.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest

pytestmark = pytest.mark.postgres_only

_RAW_POSTGRES_URL = os.getenv("ABS_TEST_POSTGRES_URL")
if not _RAW_POSTGRES_URL:
    pytest.skip(
        "ABS_TEST_POSTGRES_URL not set — RLS suite needs a live Postgres",
        allow_module_level=True,
    )
POSTGRES_URL: str = _RAW_POSTGRES_URL  # narrowed after the skip guard

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
PROJECT_ROOT = ALEMBIC_INI.parent

TABLES = ("customer_audit_entries", "webhook_events", "vault_audit_entries")


def _run_alembic(args: list[str]) -> None:
    env = os.environ.copy()
    env["ABS_DATABASE_URL"] = POSTGRES_URL
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} failed: {result.stderr}\n{result.stdout}"
    )


def _engine():
    from sqlalchemy import create_engine

    return create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="module", autouse=True)
def _migrated_database() -> Iterator[None]:
    """Run upgrade head, yield, downgrade base."""
    _run_alembic(["upgrade", "head"])
    yield
    # Best-effort cleanup; if a test broke mid-flight we still want to
    # remove the RLS policies so the next module's data is reachable.
    try:
        _run_alembic(["downgrade", "0014b_backfill_tenant_id"])
    except AssertionError:
        pass


def _seed_audit_row(conn, tenant: str) -> str:
    """Insert one row into customer_audit_entries scoped to `tenant`."""
    from sqlalchemy import text

    jti = f"jti-{uuid.uuid4().hex[:12]}"
    conn.execute(
        text(
            "INSERT INTO customer_audit_entries "
            "(license_jti, action, ts, tenant_id) "
            "VALUES (:j, 'login', :t, :tn)"
        ),
        {"j": jti, "t": datetime.now(timezone.utc), "tn": tenant},
    )
    return jti


def test_rls_blocks_cross_tenant_select() -> None:
    """Tenant A inserts; Tenant B's GUC view returns zero rows."""
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        conn.execute(text("SET abs.tenant_id = 'tenant_a'"))
        jti = _seed_audit_row(conn, "tenant_a")

    with engine.connect() as conn:
        conn.execute(text("SET abs.tenant_id = 'tenant_b'"))
        rows = conn.execute(
            text(
                "SELECT license_jti FROM customer_audit_entries "
                "WHERE license_jti = :j"
            ),
            {"j": jti},
        ).fetchall()
        assert rows == []


def test_rls_allows_same_tenant_select() -> None:
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        conn.execute(text("SET abs.tenant_id = 'tenant_a'"))
        jti = _seed_audit_row(conn, "tenant_a")

    with engine.connect() as conn:
        conn.execute(text("SET abs.tenant_id = 'tenant_a'"))
        rows = conn.execute(
            text(
                "SELECT license_jti FROM customer_audit_entries "
                "WHERE license_jti = :j"
            ),
            {"j": jti},
        ).fetchall()
        assert rows == [(jti,)]


def test_rls_no_guc_denies_all_rows() -> None:
    """FORCE RLS + no policy match (NULL current_setting) → 0 rows."""
    from sqlalchemy import text

    engine = _engine()
    # Seed under tenant_a explicitly first so the table is not empty for
    # the unrelated reasons.
    with engine.connect() as conn:
        conn.execute(text("SET abs.tenant_id = 'tenant_a'"))
        _seed_audit_row(conn, "tenant_a")

    with engine.connect() as conn:
        # Deliberately do not set abs.tenant_id. current_setting(...,true)
        # returns NULL → policy USING (tenant_id = NULL) → false for all
        # rows.
        rows = conn.execute(
            text("SELECT 1 FROM customer_audit_entries LIMIT 1")
        ).fetchall()
        assert rows == []


def test_rls_wrong_tenant_returns_zero() -> None:
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        conn.execute(text("SET abs.tenant_id = 'tenant_a'"))
        _seed_audit_row(conn, "tenant_a")

    with engine.connect() as conn:
        conn.execute(text("SET abs.tenant_id = 'does-not-exist'"))
        rows = conn.execute(
            text("SELECT 1 FROM customer_audit_entries LIMIT 1")
        ).fetchall()
        assert rows == []


def test_rls_downgrade_restores_global_visibility() -> None:
    """After downgrade past 0015 the policy is gone — all rows visible."""
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        conn.execute(text("SET abs.tenant_id = 'tenant_a'"))
        jti = _seed_audit_row(conn, "tenant_a")

    _run_alembic(["downgrade", "0014b_backfill_tenant_id"])

    try:
        with engine.connect() as conn:
            # No GUC, no policy — row must be visible.
            rows = conn.execute(
                text(
                    "SELECT license_jti FROM customer_audit_entries "
                    "WHERE license_jti = :j"
                ),
                {"j": jti},
            ).fetchall()
            assert rows == [(jti,)]
    finally:
        _run_alembic(["upgrade", "head"])
