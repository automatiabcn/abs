# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

_engine = None

# Sprint 2K — request-scoped tenant slug. The FastAPI dependency
# `set_request_tenant` (app/api/v1/tenant_guc.py) writes this at the
# start of each request; the SQLAlchemy listener below reads it just
# before every cursor execute and emits `SET LOCAL abs.tenant_id` so
# the Postgres RLS policies on the 3 audit tables see the right
# tenant. On SQLite the listener is a no-op.
current_tenant: ContextVar[str | None] = ContextVar(
    "abs_current_tenant", default=None
)


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite kullanılıyorsa DB dosyasının dizinini oluştur."""
    prefix = "sqlite:///"
    if url.startswith(prefix):
        path_str = url[len(prefix):]
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


def init_db() -> None:
    """Startup hook — tabloları oluştur."""
    # models'ı import etmek gerekiyor ki SQLModel metadata'sına kaydolsun
    from app.db import models  # noqa: F401
    from app.db import tenant_models  # noqa: F401  # T-009
    from app.auth.oauth import models as _oauth_models  # noqa: F401  # T-003

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency — request scope'lu session."""
    with Session(get_engine()) as session:
        yield session


@contextmanager
def get_session_sync() -> Iterator[Session]:
    """017 — MCP tool / non-FastAPI sync context manager.

    MCP tool'lari async ama DB query'leri sync (SQLModel + sqlite3 driver).
    `with get_session_sync() as db: ...` pattern ile session lifecycle yonet.
    """
    with Session(get_engine()) as session:
        yield session
