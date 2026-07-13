# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

logger = logging.getLogger(__name__)

_engine = None

# Request-scoped tenant slug. A FastAPI dependency writes it at the start of
# each request; the SQLAlchemy listener below reads it before every cursor
# execute and emits `SET LOCAL abs.tenant_id`, which is what makes the Postgres
# RLS policies on the audit tables resolve to the right tenant. No-op on SQLite.
current_tenant: ContextVar[str | None] = ContextVar("abs_current_tenant", default=None)


def _ensure_sqlite_dir(url: str) -> None:
    """Create the parent directory of a SQLite DB file. No-op for other engines."""
    prefix = "sqlite:///"
    if url.startswith(prefix):
        path_str = url[len(prefix) :]
        # sqlite:////abs/path → path starts with /
        Path(path_str).parent.mkdir(parents=True, exist_ok=True)


def _quote_pg_literal(value: str) -> str:
    """Escape a tenant slug for inclusion in a SET LOCAL statement.

    Tenant slugs are constrained to ``^[a-z0-9](?:[a-z0-9\\-]{0,30}[a-z0-9])?$``
    upstream, but defence-in-depth: we still single-quote and double up
    any literal quote a misbehaving caller might smuggle in. ``SET LOCAL``
    does not accept bind parameters, so the value has to land in the
    statement text.
    """
    return "'" + value.replace("'", "''") + "'"


def _set_tenant_guc(
    conn,
    cursor,
    statement,
    parameters,
    context,
    executemany,
) -> None:
    """Emit ``SET LOCAL abs.tenant_id`` before every cursor execute on Postgres.

    No-op on SQLite (the test/dev path) and when no tenant is bound to
    the ContextVar — admin BYPASSRLS connections and infrastructure
    health checks pass through untouched.
    """
    if conn.dialect.name != "postgresql":
        return
    tenant = current_tenant.get()
    if tenant is None:
        return
    cursor.execute(f"SET LOCAL abs.tenant_id = {_quote_pg_literal(tenant)}")


def _register_tenant_listener(engine) -> None:
    """Attach `_set_tenant_guc` exactly once per engine."""
    if getattr(engine, "_abs_tenant_listener_attached", False):
        return
    event.listen(engine, "before_cursor_execute", _set_tenant_guc)
    engine._abs_tenant_listener_attached = True  # type: ignore[attr-defined]


def get_engine():
    """Lazy singleton SQLModel engine."""
    global _engine
    if _engine is None:
        _ensure_sqlite_dir(settings.database_url)
        connect_args: dict = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(
            settings.database_url,
            echo=False,
            connect_args=connect_args,
        )
        _register_tenant_listener(_engine)
    return _engine


def _column_default_literal(col) -> Optional[str]:
    """A SQL literal for a column's default, for an ``ALTER TABLE ADD COLUMN``."""
    d = getattr(col, "default", None)
    if d is not None and getattr(d, "is_scalar", False):
        v = d.arg
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, str):
            return "'" + v.replace("'", "''") + "'"
    sd = getattr(col, "server_default", None)
    if sd is not None and getattr(sd, "arg", None) is not None:
        return str(getattr(sd.arg, "text", sd.arg))
    return None


def _reconcile_sqlite_columns(engine) -> None:
    """SQLite's ``create_all()`` creates missing TABLES but never ALTERs an
    existing one to add a new column. SQLite deployments skip alembic (the
    entrypoint only migrates on Postgres), so a model that gains a column would
    drift from the live table and 500 on read. This adds any model column that
    is missing from a live SQLite table — idempotent, best-effort, never fatal."""
    if engine.dialect.name != "sqlite":
        return
    try:
        insp = inspect(engine)
        live_tables = set(insp.get_table_names())
    except Exception as exc:  # pragma: no cover — never block startup
        logger.warning("sqlite reconcile: inspect failed: %s", exc)
        return
    for table in SQLModel.metadata.sorted_tables:
        if table.name not in live_tables:
            continue  # create_all just made it — fully fresh
        try:
            have = {c["name"] for c in insp.get_columns(table.name)}
        except Exception:
            continue
        for col in table.columns:
            if col.name in have:
                continue
            try:
                coltype = col.type.compile(engine.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
                default = _column_default_literal(col)
                if default is not None:
                    ddl += f" DEFAULT {default}"  # else added NULLable (SQLite OK)
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                logger.info("sqlite reconcile: added %s.%s", table.name, col.name)
            except Exception as exc:  # noqa: BLE001 — log + keep going
                logger.warning(
                    "sqlite reconcile: skip %s.%s: %s", table.name, col.name, exc
                )


def init_db() -> None:
    """Startup hook — create the tables."""
    # The model modules must be imported before create_all, or their tables are
    # missing from SQLModel's metadata and never created.
    from app.db import models  # noqa: F401
    from app.db import tenant_models  # noqa: F401
    from app.db import growth_models  # noqa: F401  # Agentic Growth domain
    from app.auth.oauth import models as _oauth_models  # noqa: F401

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    # SQLite-only: reconcile columns added to existing tables (create_all won't).
    _reconcile_sqlite_columns(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency — one session per request."""
    with Session(get_engine()) as session:
        yield session


@contextmanager
def get_session_sync() -> Iterator[Session]:
    """Sync session context manager for callers outside FastAPI (MCP tools).

    Those callers are async, but the DB layer is sync (SQLModel + the sqlite3
    driver), so they need an explicit `with get_session_sync() as db:` block to
    bound the session lifetime.
    """
    with Session(get_engine()) as session:
        yield session
