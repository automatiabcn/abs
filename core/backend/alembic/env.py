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


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _resolved_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
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
