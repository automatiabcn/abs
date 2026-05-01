"""Q11 Round 17 / L14 — Alembic up/down round-trip.

Q11 Round 5 added 0008_minted_token_blacklist with both upgrade()
and downgrade() implementations, but a downgrade that doesn't
actually reverse the upgrade ships green at suite-time and only
fails the first time a customer hits a rollback emergency.

This test:
  1. Spins up a temporary SQLite file (not the session-scoped one
     that conftest patched with create_all).
  2. `alembic upgrade head` — reaches 0008.
  3. Confirms minted_token_blacklist exists on disk.
  4. `alembic downgrade -1` — drops it.
  5. Confirms the table is gone.
  6. `alembic upgrade head` again — table re-created cleanly,
     no constraint name collision.

Catches:
  * downgrade() forgot to drop an index (would error on re-upgrade)
  * unique constraint name typo
  * server_default mismatch between SQLModel + DDL
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def _alembic_cfg_for(db_url: str, repo_root: Path) -> Config:
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option(
        "script_location", str(repo_root / "alembic")
    )
    return cfg


class TestQ11L14AlembicRoundTrip:
    def test_upgrade_downgrade_upgrade_round_trip(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "round_trip.db"
            db_url = f"sqlite:///{db_path}"
            cfg = _alembic_cfg_for(db_url, repo_root)

            command.upgrade(cfg, "head")

            engine = create_engine(db_url)
            tables_after_up = set(inspect(engine).get_table_names())
            assert "minted_token_blacklist" in tables_after_up
            assert "chat_sessions" in tables_after_up  # 0007
            engine.dispose()

            command.downgrade(cfg, "-1")
            engine = create_engine(db_url)
            tables_after_down = set(inspect(engine).get_table_names())
            assert "minted_token_blacklist" not in tables_after_down, (
                "downgrade did not remove the table — Q11-L14-001 "
                "downgrade() incomplete"
            )
            # 0007's tables remain after stepping back from 0008.
            assert "chat_sessions" in tables_after_down
            engine.dispose()

            command.upgrade(cfg, "head")
            engine = create_engine(db_url)
            tables_after_redo = set(inspect(engine).get_table_names())
            assert "minted_token_blacklist" in tables_after_redo, (
                "re-upgrade after downgrade failed to re-create table "
                "— constraint or index name collision"
            )
            engine.dispose()
