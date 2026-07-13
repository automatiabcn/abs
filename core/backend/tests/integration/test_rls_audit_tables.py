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

# Sprint 2N.2 FAZ D: data ops run as a non-superuser, non-BYPASSRLS role
# so the RLS policies actually filter. Falls back to POSTGRES_URL when the
# RLS-specific URL isn't set (legacy single-role test runs continue to
# work, just don't exercise RLS the same way).
_RAW_RLS_URL = os.getenv("ABS_TEST_POSTGRES_RLS_URL")
RLS_URL: str = _RAW_RLS_URL or POSTGRES_URL

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
    # Sprint 2N.2 FAZ D: NullPool prevents connection reuse across the
    # `with engine.connect()` blocks the tests use. Without it, the
    # second connect() inherits the prior block's SET abs.tenant_id
    # GUC from the pooled connection and the "no GUC" assertions fail.
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    return create_engine(RLS_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)


def _admin_engine():
    """Migration-tier connection that retains DDL/role privileges."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    return create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)


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
                "SELECT license_jti FROM customer_audit_entries WHERE license_jti = :j"
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
                "SELECT license_jti FROM customer_audit_entries WHERE license_jti = :j"
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

    # Sprint 2N.2 FAZ D: migration 0015b's downgrade intentionally runs
    # `DROP ROLE IF EXISTS abs_admin` without revoking grants first
    # (prod safety: a live admin connection must not be silently
    # stripped). CI granted abs_admin SELECT/CONNECT/USAGE, so the
    # naked DROP fails with DependentObjectsStillExist. REVOKE through
    # the SUPERUSER admin engine (the grantor) before triggering the
    # alembic downgrade so 0015b's DROP ROLE succeeds.
    with _admin_engine().connect() as conn:
        conn.execute(
            text(
                "REVOKE SELECT ON customer_audit_entries, "
                "webhook_events, vault_audit_entries FROM abs_admin"
            )
        )
        conn.execute(text("REVOKE USAGE ON SCHEMA public FROM abs_admin"))
        conn.execute(text("REVOKE CONNECT ON DATABASE abs_rls_test FROM abs_admin"))

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
        # Re-grant the abs_admin permissions that the downgrade dropped
        # so the BYPASSRLS suite that runs after this module still works.
        # Migration 0015b creates abs_admin WITH NOLOGIN — also re-apply
        # the LOGIN attribute + password that the CI workflow normally
        # sets once after the first upgrade. Goes through _admin_engine
        # because abs_app_rls cannot ALTER ROLE / GRANT.
        with _admin_engine().connect() as conn:
            conn.execute(text("ALTER ROLE abs_admin WITH LOGIN PASSWORD 'abs_admin'"))
            conn.execute(text("GRANT CONNECT ON DATABASE abs_rls_test TO abs_admin"))
            conn.execute(text("GRANT USAGE ON SCHEMA public TO abs_admin"))
            conn.execute(
                text(
                    "GRANT SELECT ON customer_audit_entries, "
                    "webhook_events, vault_audit_entries TO abs_admin"
                )
            )
