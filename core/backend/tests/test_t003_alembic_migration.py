"""T-003 / T-007 — Alembic migration upgrade/downgrade smoke test."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

pytest.importorskip("alembic")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _config_for(db_url: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_alembic_upgrade_creates_oauth_tables(tmp_path) -> None:
    db = tmp_path / "abs.db"
    url = f"sqlite:///{db}"
    cfg = _config_for(url)

    command.upgrade(cfg, "head")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert {
        "oauth_clients",
        "oauth_auth_codes",
        "oauth_refresh_tokens",
    } <= tables


def test_alembic_downgrade_drops_oauth_tables(tmp_path) -> None:
    db = tmp_path / "abs.db"
    url = f"sqlite:///{db}"
    cfg = _config_for(url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert "oauth_clients" not in tables
    assert "oauth_auth_codes" not in tables
    assert "oauth_refresh_tokens" not in tables
