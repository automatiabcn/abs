# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Sprint 2K — RLS chaos: dropping the tenant GUC mid-request → 403.

Two layers of coverage:

    1. Default lane (SQLite, fast): mock DBAPIError carrying SQLSTATE
       42501 + the "row-level security" message and confirm the
       handler converts it to a typed 403. Asserts the lifeguard works
       in isolation.

    2. Postgres-only lane: real INSERT after an explicit
       ``RESET abs.tenant_id`` simulates a connection that forgot to
       set the GUC. The DB rejects the row; FastAPI returns 403.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError


# ───── default lane — unit ────────────────────────────────────────────


def _build_minimal_app() -> FastAPI:
    """Tiny app wired with only the RLS handler so the test stays fast."""
    from app.middleware.rls_violation_handler import install_rls_violation_handler

    app = FastAPI()
    install_rls_violation_handler(app)

    @app.get("/raises-rls")
    def _raises_rls():
        orig = MagicMock()
        orig.pgcode = "42501"
        orig.__str__ = lambda self: (
            "new row violates row-level security policy for table "
            '"customer_audit_entries"'
        )
        raise DBAPIError("INSERT INTO ...", {}, orig)

    @app.get("/raises-other")
    def _raises_other():
        orig = MagicMock()
        orig.pgcode = "23505"  # unique_violation, not RLS
        orig.__str__ = lambda self: "duplicate key value violates unique constraint"
        raise DBAPIError("INSERT INTO ...", {}, orig)

    return app


def test_rls_violation_returns_403_with_typed_detail() -> None:
    client = TestClient(_build_minimal_app(), raise_server_exceptions=False)
    resp = client.get("/raises-rls")
    assert resp.status_code == 403
    assert resp.json() == {"detail": "tenant_isolation_required"}


def test_non_rls_db_error_falls_through() -> None:
    """Other DB errors keep their existing 500 behaviour, not 403."""
    client = TestClient(_build_minimal_app(), raise_server_exceptions=False)
    resp = client.get("/raises-other")
    assert resp.status_code == 500
    # detail should not be tenant_isolation_required.
    body = (
        resp.json()
        if resp.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    assert body.get("detail") != "tenant_isolation_required"


def test_rls_message_match_without_sqlstate() -> None:
    """A driver that omits pgcode but keeps the message still triggers 403."""
    from app.middleware.rls_violation_handler import _is_rls_violation

    orig = MagicMock()
    orig.pgcode = None
    orig.__str__ = lambda self: "row-level security policy"
    exc = DBAPIError("INSERT ...", {}, orig)
    assert _is_rls_violation(exc) is True


# ───── postgres_only lane — end-to-end ────────────────────────────────


@pytest.mark.postgres_only
def test_drop_guc_mid_request_returns_403_against_real_db() -> None:
    _raw = os.getenv("ABS_TEST_POSTGRES_URL")
    if not _raw:
        pytest.skip("ABS_TEST_POSTGRES_URL not set")

    from sqlalchemy import create_engine, text

    engine = create_engine(_raw, isolation_level="AUTOCOMMIT")

    marker = uuid.uuid4().hex[:12]
    with engine.connect() as conn:
        # Simulate a request that *forgot* to pin the GUC. The migration
        # policy has WITH CHECK; the INSERT must be rejected with
        # SQLSTATE 42501.
        conn.execute(text("RESET abs.tenant_id"))
        with pytest.raises(DBAPIError) as ei:
            conn.execute(
                text(
                    "INSERT INTO customer_audit_entries "
                    "(license_jti, action, ts, tenant_id) "
                    "VALUES (:j, 'login', :t, 'acme')"
                ),
                {"j": f"jti-chaos-{marker}", "t": datetime.now(timezone.utc)},
            )

    # And the handler maps that to a 403 at the API layer — verified by
    # the matching unit test above; we don't spin up the full app here
    # to keep the postgres lane focused on the DB contract.
    orig = ei.value.orig
    pgcode = getattr(orig, "pgcode", None)
    assert pgcode in ("42501", None)
    assert "row-level security" in str(orig).lower()
