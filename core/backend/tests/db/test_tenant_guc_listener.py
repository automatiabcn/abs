# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Sprint 2K — SQLAlchemy GUC listener + FastAPI tenant dep + worker scope.

The listener emits ``SET LOCAL abs.tenant_id`` on Postgres only; SQLite
is no-op. These tests use a Postgres-flavoured fake cursor (no live DB
needed) so the suite stays in the default lane while still exercising
the dialect branch.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.db.session import (
    _set_tenant_guc,
    current_tenant,
)


class _FakeDialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeConn:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = _FakeDialect(dialect_name)


class _RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...] | None]] = []

    def execute(self, sql: str, params: Any | None = None) -> None:
        self.statements.append((sql, params))


def _call_listener(dialect: str) -> _RecordingCursor:
    cur = _RecordingCursor()
    _set_tenant_guc(
        _FakeConn(dialect), cur, "SELECT 1", {}, None, False
    )
    return cur


def test_postgres_with_tenant_emits_set_local() -> None:
    token = current_tenant.set("acme")
    try:
        cur = _call_listener("postgresql")
    finally:
        current_tenant.reset(token)

    assert cur.statements == [("SET LOCAL abs.tenant_id = 'acme'", None)]


def test_postgres_without_tenant_skips_emit() -> None:
    assert current_tenant.get() is None
    cur = _call_listener("postgresql")
    assert cur.statements == []


def test_sqlite_dialect_is_no_op_even_with_tenant() -> None:
    token = current_tenant.set("acme")
    try:
        cur = _call_listener("sqlite")
    finally:
        current_tenant.reset(token)

    assert cur.statements == []


def test_quote_escapes_smuggled_quote() -> None:
    # Realistically the upstream slug regex blocks quotes, but
    # defence-in-depth: a malformed slug must not break out of the
    # literal. Double-up single quotes per SQL spec.
    token = current_tenant.set("ev'il")
    try:
        cur = _call_listener("postgresql")
    finally:
        current_tenant.reset(token)

    assert cur.statements == [("SET LOCAL abs.tenant_id = 'ev''il'", None)]


def test_concurrent_contextvar_isolation_under_asyncio_gather() -> None:
    """Two tasks setting different tenants must not bleed."""

    results: list[str | None] = []

    async def task(slug: str) -> None:
        token = current_tenant.set(slug)
        try:
            await asyncio.sleep(0)  # yield to the other task
            results.append(current_tenant.get())
        finally:
            current_tenant.reset(token)

    async def main() -> None:
        await asyncio.gather(task("acme"), task("globex"))

    asyncio.run(main())
    assert sorted(results) == ["acme", "globex"]


def test_with_tenant_scope_sets_and_resets() -> None:
    from app.api.v1.tenant_guc import with_tenant

    assert current_tenant.get() is None
    with with_tenant("acme"):
        assert current_tenant.get() == "acme"
    assert current_tenant.get() is None


def test_with_tenant_none_keeps_var_unset() -> None:
    from app.api.v1.tenant_guc import with_tenant

    assert current_tenant.get() is None
    with with_tenant(None):
        # Service / cross-tenant worker — must not pin a slug.
        assert current_tenant.get() is None
    assert current_tenant.get() is None


@pytest.mark.asyncio
async def test_set_request_tenant_admin_no_tenant_yields_without_pin() -> None:
    """Admin sessions without a tenant pass through (BYPASSRLS path).

    The dep yields once; ContextVar must remain unset.
    """
    from app.api.v1.deps import AuthContext
    from app.api.v1.tenant_guc import set_request_tenant

    admin = AuthContext(
        subject="ops@local",
        tenant_id=None,
        roles=["admin"],
        raw_claims={},
    )

    gen = set_request_tenant(auth=admin)
    await gen.__anext__()  # enter
    assert current_tenant.get() is None
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()  # exit
    assert current_tenant.get() is None


@pytest.mark.asyncio
async def test_set_request_tenant_member_no_tenant_403() -> None:
    """Non-admin with no tnt claim must get 403, not silently bypass."""
    from fastapi import HTTPException

    from app.api.v1.deps import AuthContext
    from app.api.v1.tenant_guc import set_request_tenant

    member = AuthContext(
        subject="user@acme",
        tenant_id=None,
        roles=["member"],
        raw_claims={},
    )

    gen = set_request_tenant(auth=member)
    with pytest.raises(HTTPException) as ei:
        await gen.__anext__()
    assert ei.value.status_code == 403
    assert ei.value.detail == "tenant_isolation_required"


@pytest.mark.asyncio
async def test_set_request_tenant_member_with_tenant_pins_and_resets() -> None:
    from app.api.v1.deps import AuthContext
    from app.api.v1.tenant_guc import set_request_tenant

    member = AuthContext(
        subject="user@acme",
        tenant_id="acme",
        roles=["member"],
        raw_claims={"tnt": "acme"},
    )

    gen = set_request_tenant(auth=member)
    await gen.__anext__()
    assert current_tenant.get() == "acme"
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
    assert current_tenant.get() is None
