"""T-003/T-007 — Alembic environment.

Loads SQLModel metadata so `alembic revision --autogenerate` picks up
ABS models. URL is read from app settings rather than alembic.ini so
the same migration script works in dev/prod.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Make `app.*` importable when alembic runs from core/backend/.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.db import models as _abs_models  # noqa: F401,E402  — register tables
from app.db import tenant_models as _tenant_models  # noqa: F401,E402  # T-009
from app.auth.oauth import models as _oauth_models  # noqa: F401,E402

config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False — without this, fileConfig silences every
    # app.* logger that was already created (e.g. app.vault.runner), which
    # breaks caplog assertions in the rest of the test suite.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = SQLModel.metadata


def _resolved_url() -> str:
    return config.get_main_option("sqlalchemy.url") or settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_resolved_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


_LEGACY_REVISION_REMAP = {
    # Sprint 2N.1: revision IDs must fit Alembic's default VARCHAR(32)
    # alembic_version column. Rewrite the only legacy long ID before the
    # migration runner reads its current state.
    "0012_tenant_settings_and_fk_cascades": "0012_tenant_settings_fk",
}


def _rewrite_legacy_alembic_version(connection) -> None:
    """Rewrite legacy long revision IDs in alembic_version.

    Runs before ``context.configure`` and must leave the connection
    in *no* implicit transaction state, otherwise Alembic's outer
    ``begin_transaction`` becomes a savepoint and the migration commit
    is dropped when the connect-block exits.
    """
    from sqlalchemy import text

    dialect = connection.dialect.name
    if dialect == "sqlite":
        table_check = text(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='alembic_version' LIMIT 1"
        )
    else:
        table_check = text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'alembic_version' LIMIT 1"
        )
    has_table = connection.execute(table_check).first()
    if has_table is None:
        connection.rollback()
        return
    rows = connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).fetchall()
    needs_update = any(current in _LEGACY_REVISION_REMAP for (current,) in rows)
    if needs_update:
        for (current,) in rows:
            if current in _LEGACY_REVISION_REMAP:
                connection.execute(
                    text(
                        "UPDATE alembic_version SET version_num=:new "
                        "WHERE version_num=:old"
                    ),
                    {"new": _LEGACY_REVISION_REMAP[current], "old": current},
                )
        connection.commit()
    else:
        connection.rollback()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _resolved_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _rewrite_legacy_alembic_version(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
