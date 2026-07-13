# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Sprint 2K — convert Postgres RLS violations to a typed 403 response.

When the tenant GUC is missing or wrong at write time, Postgres raises
``new row violates row-level security policy`` (SQLSTATE 42501,
``InsufficientPrivilege``). Left uncaught that bubbles up to FastAPI's
default 500 path and the client sees an unhelpful "internal server
error" while the operator scans logs for a database crash.

This handler intercepts those errors and re-raises them as a clean
``403 tenant_isolation_required``. Read-side leaks are *already*
prevented (the policy silently filters rows) — this handler is the
write-side complement.
"""

from __future__ import annotations

import logging
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

logger = logging.getLogger(__name__)


# Postgres surfaces RLS violations through psycopg2 with SQLSTATE 42501
# *and* an error message containing "row-level security policy". We
# match defensively on both so the handler still works if a future
# driver carries one signal but not the other.
_PG_INSUFFICIENT_PRIVILEGE_SQLSTATE = "42501"
_RLS_MSG_RE = re.compile(r"row-level security", re.IGNORECASE)


def _is_rls_violation(exc: DBAPIError) -> bool:
    sqlstate = getattr(getattr(exc, "orig", None), "pgcode", None)
    if sqlstate == _PG_INSUFFICIENT_PRIVILEGE_SQLSTATE:
        return True
    msg = str(getattr(exc, "orig", "")) or str(exc)
    return bool(_RLS_MSG_RE.search(msg))


def install_rls_violation_handler(app: FastAPI) -> None:
    """Register the handler on the given FastAPI app."""

    @app.exception_handler(DBAPIError)
    async def _on_db_error(request: Request, exc: DBAPIError) -> JSONResponse:
        if _is_rls_violation(exc):
            # Don't echo the underlying message — it can include row
            # values that the caller is supposed to be denied.
            logger.warning(
                "rls_violation path=%s method=%s",
                request.url.path,
                request.method,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "tenant_isolation_required"},
            )
        # Non-RLS DB errors keep their existing 500 fall-through path —
        # re-raise so FastAPI's default handler logs + responds.
        raise exc
