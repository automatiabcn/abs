# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sprint 2K — FastAPI dependency that pins the request tenant.

The auth pipeline already decodes the JWT and exposes the principal via
``AuthContext`` (``app.api.v1.deps``). This dep is a thin adapter on top:
it pulls the ``tnt`` claim, writes it to the request-scoped ContextVar
that ``app.db.session._set_tenant_guc`` reads, and yields. Once the
request completes the ContextVar is reset so a pool connection cannot
leak the slug into a subsequent unrelated request.

Admin sessions (``roles=["admin"]``) with no tenant — i.e. the operator
console mounting the system-wide audit view — fall through without
setting the GUC. Production deployments grant those sessions the
``abs_admin`` Postgres role which carries ``BYPASSRLS``; dev/test runs
on SQLite (no RLS engine) so the bypass is implicit. Bearer principals
without a ``tnt`` claim that are not admins get a 403 because they have
nothing safe to do against an RLS-protected table.
"""

from __future__ import annotations

from contextvars import Token
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status

from app.api.v1.deps import AuthContext, get_auth_context
from app.db.session import current_tenant


__all__ = ["set_request_tenant", "with_tenant"]


async def set_request_tenant(
    auth: AuthContext = Depends(get_auth_context),
) -> AsyncGenerator[None, None]:
    """Pin the principal's tenant to the request ContextVar.

    Yields nothing — callers use the dep purely for its side effect.
    The ContextVar is reset on dep teardown so the connection pool does
    not bleed slugs across requests.
    """
    tenant = auth.tenant_id
    is_admin = "admin" in (auth.roles or [])

    if tenant is None and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_isolation_required",
        )

    token: Token[str | None] | None = None
    if tenant is not None:
        token = current_tenant.set(tenant)
    try:
        yield
    finally:
        if token is not None:
            current_tenant.reset(token)


def with_tenant(tenant: str | None):
    """Inngest / background-worker helper.

    Usage::

        async def handler(payload):
            with with_tenant(payload.get("tenant_id")):
                await do_work()

    Skips the GUC write when ``tenant`` is None so jobs that genuinely
    operate across tenants (e.g. the audit-log compaction worker) keep
    relying on the ``abs_admin`` role's ``BYPASSRLS``.
    """

    class _Scope:
        def __enter__(self) -> None:
            self._token: Token[str | None] | None = None
            if tenant is not None:
                self._token = current_tenant.set(tenant)

        def __exit__(self, exc_type, exc, tb) -> None:
            if self._token is not None:
                current_tenant.reset(self._token)

    return _Scope()
