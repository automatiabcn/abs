# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Sprint 2K — verify abs_admin BYPASSRLS sees every tenant.

Postgres-only. The default lane (SQLite) skips this module via the
``postgres_only`` marker plus the env-var guard.
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
_RAW_ADMIN_URL = os.getenv("ABS_TEST_POSTGRES_ADMIN_URL")
if not (_RAW_POSTGRES_URL and _RAW_ADMIN_URL):
    pytest.skip(
        "ABS_TEST_POSTGRES_URL + ABS_TEST_POSTGRES_ADMIN_URL needed for the "
        "abs_admin BYPASSRLS suite",
        allow_module_level=True,
    )

POSTGRES_URL: str = _RAW_POSTGRES_URL
ADMIN_URL: str = _RAW_ADMIN_URL

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
PROJECT_ROOT = ALEMBIC_INI.parent


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


@pytest.fixture(scope="module", autouse=True)
def _migrated_database() -> Iterator[None]:
    _run_alembic(["upgrade", "head"])
    yield


def _engine(url: str):
    from sqlalchemy import create_engine

    return create_engine(url, isolation_level="AUTOCOMMIT")


def test_abs_admin_sees_rows_across_tenants() -> None:
    """Two tenants, two rows; abs_admin SELECT returns both."""
    from sqlalchemy import text

    app_engine = _engine(POSTGRES_URL)
    admin_engine = _engine(ADMIN_URL)

    marker = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)

    with app_engine.connect() as conn:
        for tenant in ("acme", "globex"):
            conn.execute(text("SET abs.tenant_id = :tn"), {"tn": tenant})
            conn.execute(
                text(
                    "INSERT INTO customer_audit_entries "
                    "(license_jti, action, ts, tenant_id) "
                    "VALUES (:j, :a, :t, :tn)"
                ),
                {
                    "j": f"jti-{marker}-{tenant}",
                    "a": "login",
                    "t": now,
                    "tn": tenant,
                },
            )

    with admin_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tenant_id FROM customer_audit_entries "
                "WHERE license_jti LIKE :p ORDER BY tenant_id"
            ),
            {"p": f"jti-{marker}-%"},
        ).fetchall()
        assert [r[0] for r in rows] == ["acme", "globex"]


def test_abs_app_blocked_without_guc() -> None:
    """Regression guard — abs_app must hit the policy even when admin runs above."""
    from sqlalchemy import text

    app_engine = _engine(POSTGRES_URL)

    marker = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)

    with app_engine.connect() as conn:
        conn.execute(text("SET abs.tenant_id = 'acme'"))
        conn.execute(
            text(
                "INSERT INTO customer_audit_entries "
                "(license_jti, action, ts, tenant_id) "
                "VALUES (:j, 'login', :t, 'acme')"
            ),
            {"j": f"jti-{marker}", "t": now},
        )

    with app_engine.connect() as conn:
        # No GUC — abs_app must see nothing under FORCE RLS.
        rows = conn.execute(
            text(
                "SELECT 1 FROM customer_audit_entries "
                "WHERE license_jti = :j"
            ),
            {"j": f"jti-{marker}"},
        ).fetchall()
        assert rows == []
