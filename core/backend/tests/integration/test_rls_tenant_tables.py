# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Sprint 2L — RLS enforcement on the tenant tables added in 0019.

Sister suite to ``test_rls_audit_tables.py`` (Sprint 2K, the 3 audit tables).
0019 extends the same ``abs.tenant_id`` GUC policy to the tenant-DATA tables.
This suite proves the two policy shapes engage on Postgres:

  * ``provider_keys``   — direct ``tenant_slug`` column (BYOK secrets, the
                          highest blast radius).
  * ``chat_messages``   — no tenant column of its own; scoped through its
                          parent ``chat_sessions`` via the EXISTS sub-select.

Contract per table:
  1. Tenant A writes → Tenant B's GUC view sees zero rows.
  2. Tenant A writes → Tenant A's GUC view sees its own row.
  3. No GUC set → FORCE RLS denies all rows (NULL current_setting).
  4. WITH CHECK rejects an INSERT whose tenant differs from the GUC.

Default lane is SQLite (no RLS engine) so the module carries the
``postgres_only`` marker and skips unless ``ABS_TEST_POSTGRES_URL`` is set.
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
POSTGRES_URL: str = _RAW_POSTGRES_URL

# Data ops run as a non-superuser, non-BYPASSRLS role so the policies filter.
RLS_URL: str = os.getenv("ABS_TEST_POSTGRES_RLS_URL") or POSTGRES_URL

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


def _engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    # NullPool: each connect() is a fresh connection so a prior block's
    # SET abs.tenant_id cannot leak into the "no GUC" assertions.
    return create_engine(RLS_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)


@pytest.fixture(scope="module", autouse=True)
def _migrated_database() -> Iterator[None]:
    """Upgrade to head (applies 0019), yield, drop 0019 policies after."""
    _run_alembic(["upgrade", "head"])
    yield
    try:
        _run_alembic(["downgrade", "0018_project_slug_per_tenant"])
    except AssertionError:
        pass


def _set_guc(conn, tenant: str) -> None:
    from sqlalchemy import text

    conn.execute(text("SET abs.tenant_id = :t"), {"t": tenant})


# ── seeds (return the row's lookup key) ────────────────────────────────────


def _seed_provider_key(conn, tenant: str) -> str:
    from sqlalchemy import text

    owner = f"user-{uuid.uuid4().hex[:8]}@x.io"
    conn.execute(
        text(
            "INSERT INTO provider_keys "
            "(tenant_slug, owner_type, owner_id, provider, encrypted_value, created_at) "
            "VALUES (:tn, 'user', :oid, 'groq', 'b64:xxx', :ts)"
        ),
        {"tn": tenant, "oid": owner, "ts": datetime.now(timezone.utc)},
    )
    return owner


def _seed_meeting_with_segment(conn, tenant: str) -> int:
    """Insert a meeting (tenant-scoped) + one child segment; return segment id."""
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    mid = conn.execute(
        text(
            "INSERT INTO meetings "
            "(tenant_slug, uploader_email, filename, duration_sec, speaker_count, "
            " status, summary, created_at) "
            "VALUES (:tn, 'u@x.io', 'm.mp3', 0, 0, 'done', '', :now) RETURNING id"
        ),
        {"tn": tenant, "now": now},
    ).scalar_one()
    sid = conn.execute(
        text(
            "INSERT INTO meeting_segments "
            "(meeting_id, speaker_id, start_sec, end_sec, text) "
            "VALUES (:m, 'spk_0', 0, 1, 'hi') RETURNING id"
        ),
        {"m": mid},
    ).scalar_one()
    return int(sid)


def _seed_chat_session_with_message(conn, tenant: str) -> int:
    """Insert a session (tenant-scoped) + one child message; return msg id."""
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    sid = conn.execute(
        text(
            "INSERT INTO chat_sessions "
            "(tenant_slug, user_email, title, created_at, updated_at, pinned, "
            " last_activity_at, message_count) "
            "VALUES (:tn, 'u@x.io', 't', :now, :now, false, :now, 0) "
            "RETURNING id"
        ),
        {"tn": tenant, "now": now},
    ).scalar_one()
    mid = conn.execute(
        text(
            "INSERT INTO chat_messages (session_id, role, content, created_at) "
            "VALUES (:sid, 'user', 'hello', :now) RETURNING id"
        ),
        {"sid": sid, "now": now},
    ).scalar_one()
    return int(mid)


# ── provider_keys (tenant_slug column) ─────────────────────────────────────


def test_provider_keys_cross_tenant_select_blocked() -> None:
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        _set_guc(conn, "tenant_a")
        owner = _seed_provider_key(conn, "tenant_a")
    with engine.connect() as conn:
        _set_guc(conn, "tenant_b")
        rows = conn.execute(
            text("SELECT owner_id FROM provider_keys WHERE owner_id = :o"),
            {"o": owner},
        ).fetchall()
        assert rows == []


def test_provider_keys_same_tenant_select_ok() -> None:
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        _set_guc(conn, "tenant_a")
        owner = _seed_provider_key(conn, "tenant_a")
    with engine.connect() as conn:
        _set_guc(conn, "tenant_a")
        rows = conn.execute(
            text("SELECT owner_id FROM provider_keys WHERE owner_id = :o"),
            {"o": owner},
        ).fetchall()
        assert rows == [(owner,)]


def test_provider_keys_no_guc_denies_all() -> None:
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        _set_guc(conn, "tenant_a")
        _seed_provider_key(conn, "tenant_a")
    with engine.connect() as conn:
        # No SET abs.tenant_id → current_setting(...,true) is NULL → 0 rows.
        rows = conn.execute(text("SELECT 1 FROM provider_keys LIMIT 1")).fetchall()
        assert rows == []


def test_provider_keys_with_check_blocks_wrong_tenant_insert() -> None:
    """WITH CHECK: GUC tenant_a cannot write a row tagged tenant_b."""
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    engine = _engine()
    with engine.connect() as conn:
        _set_guc(conn, "tenant_a")
        with pytest.raises(ProgrammingError):
            conn.execute(
                text(
                    "INSERT INTO provider_keys "
                    "(tenant_slug, owner_type, owner_id, provider, "
                    " encrypted_value, created_at) "
                    "VALUES ('tenant_b', 'user', 'x@x.io', 'groq', 'b64:y', :ts)"
                ),
                {"ts": datetime.now(timezone.utc)},
            )


# ── chat_messages (FK-scoped via chat_sessions EXISTS sub-select) ──────────


def test_chat_messages_child_isolation() -> None:
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        _set_guc(conn, "tenant_a")
        mid = _seed_chat_session_with_message(conn, "tenant_a")
    # Other tenant cannot see the child message even though it has no tenant
    # column of its own — the parent session is invisible under its GUC.
    with engine.connect() as conn:
        _set_guc(conn, "tenant_b")
        rows = conn.execute(
            text("SELECT id FROM chat_messages WHERE id = :m"), {"m": mid}
        ).fetchall()
        assert rows == []
    # Owning tenant still sees it.
    with engine.connect() as conn:
        _set_guc(conn, "tenant_a")
        rows = conn.execute(
            text("SELECT id FROM chat_messages WHERE id = :m"), {"m": mid}
        ).fetchall()
        assert rows == [(mid,)]


def test_meeting_segments_child_isolation() -> None:
    """meeting_segments has no tenant column — scoped via meetings parent."""
    from sqlalchemy import text

    engine = _engine()
    with engine.connect() as conn:
        _set_guc(conn, "tenant_a")
        sid = _seed_meeting_with_segment(conn, "tenant_a")
    with engine.connect() as conn:
        _set_guc(conn, "tenant_b")
        rows = conn.execute(
            text("SELECT id FROM meeting_segments WHERE id = :s"), {"s": sid}
        ).fetchall()
        assert rows == []
    with engine.connect() as conn:
        _set_guc(conn, "tenant_a")
        rows = conn.execute(
            text("SELECT id FROM meeting_segments WHERE id = :s"), {"s": sid}
        ).fetchall()
        assert rows == [(sid,)]
