# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""SQLite column reconciler — the create_all-doesn't-ALTER deploy guard.

Simulates a live SQLite deployment (a self-host box) whose ``connector_states`` predates
the Stage A credential columns: on the next boot the reconciler must ADD them so
reads don't 500. Idempotent on a second run."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.db.session import _reconcile_sqlite_columns

_OLD_CONNECTOR_STATES = (
    "CREATE TABLE connector_states ("
    " id INTEGER PRIMARY KEY,"
    " tenant_slug VARCHAR(64),"
    " connector_id VARCHAR(48),"
    " status VARCHAR(16),"
    " health INTEGER,"
    " connected_at DATETIME,"
    " last_sync_at DATETIME)"
)
_STAGE_A_COLUMNS = ("auth_kind", "encrypted_credentials", "last_sync_count", "last_error")


def test_reconcile_adds_missing_columns(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text(_OLD_CONNECTOR_STATES))

    before = {col["name"] for col in inspect(eng).get_columns("connector_states")}
    assert not any(c in before for c in _STAGE_A_COLUMNS)

    _reconcile_sqlite_columns(eng)

    after = {col["name"] for col in inspect(eng).get_columns("connector_states")}
    for col in _STAGE_A_COLUMNS:
        assert col in after, f"reconciler did not add {col}"

    # the row survives + a read of the new column works (no 500)
    with eng.begin() as c:
        c.execute(text("INSERT INTO connector_states (tenant_slug, connector_id) VALUES ('t','x')"))
        row = c.execute(text("SELECT auth_kind, last_sync_count FROM connector_states")).first()
    assert row is not None


def test_reconcile_is_idempotent(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'idem.db'}")
    with eng.begin() as c:
        c.execute(text(_OLD_CONNECTOR_STATES))
    _reconcile_sqlite_columns(eng)
    cols1 = {col["name"] for col in inspect(eng).get_columns("connector_states")}
    _reconcile_sqlite_columns(eng)          # second run must be a no-op, not raise
    cols2 = {col["name"] for col in inspect(eng).get_columns("connector_states")}
    assert cols1 == cols2


def test_reconcile_noops_on_non_sqlite():
    class _FakeDialect:
        name = "postgresql"

    class _FakeEngine:
        dialect = _FakeDialect()

    # must return immediately without touching anything
    _reconcile_sqlite_columns(_FakeEngine())
