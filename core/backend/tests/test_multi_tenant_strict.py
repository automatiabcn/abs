# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""ABS_MULTI_TENANT_STRICT — strict-isolation gate for shared SaaS.

Two latent fail-open paths are harmless on single-tenant self-host
but would leak across tenants on a shared multi-tenant SaaS instance. They are
closed *only* when the operator opts into strict mode, so single-tenant
behaviour (and its existing tests) stay byte-identical:

  1. marketplace install/list — a claim-less admin can pass an arbitrary
     ``tenant=`` body/query value and store/read under it (fail-open). Strict
     mode forces the principal's own resolved tenant.
  2. graph /cypher + /nl-query — raw Cypher can RETURN scalar/aliased
     properties that carry no ``tenant_id`` key, slipping past the row filter.
     Strict mode refuses the raw surface (templated endpoints stay open).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import marketplace as marketplace_routes
from app.api.v1.deps import AuthContext, get_admin_or_bearer_auth_context
from app.config import settings
from app.main import app


@pytest.fixture()
def strict_on(monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant_strict", True)
    yield


@pytest.fixture()
def strict_off(monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant_strict", False)
    yield


# --------------------------------------------------------------------------
# marketplace — claim-less admin must not install under an arbitrary tenant
# --------------------------------------------------------------------------


@pytest.fixture()
def claimless_admin():
    """An admin with no tenant claim and no users-row / credentials source →
    ``_resolve_admin_tenant`` falls back to 'default'."""
    app.dependency_overrides[marketplace_routes.current_admin] = lambda: {
        "sub": "owner@acme-co.io"
    }
    try:
        yield
    finally:
        app.dependency_overrides.pop(marketplace_routes.current_admin, None)


def test_strict_blocks_claimless_install_to_foreign_tenant(
    client: TestClient, claimless_admin, strict_on
) -> None:
    """Strict ON, end-to-end: a claim-less admin (resolved tenant 'default')
    POSTing an install under 'acme-co' is cross-tenant → 403. A rejected
    install persists nothing, so this stays hermetic (no install-store leak)."""
    r = client.post(
        "/v1/marketplace/install",
        json={"plugin_id": "slack-receiver", "tenant": "acme-co"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "cross_tenant_forbidden"


# The "allow own tenant" + "legacy fail-open" paths are asserted at the unit
# level on `_enforce_tenant_match` so the test never writes to the
# process-global install store (which an unrelated marketplace-lifecycle test
# reads). A real install would leak across tests; the gate logic is what we
# actually need to pin.


def test_gate_allows_own_resolved_tenant_in_strict(strict_on):
    """Strict ON: claim-less admin resolving to 'default' may target 'default'
    — the gate does not raise."""
    from app.api.marketplace import _enforce_tenant_match

    # no claim, no users-row/creds source → _resolve_admin_tenant → 'default'
    _enforce_tenant_match({"sub": "owner@acme-co.io"}, "default")  # no raise


def test_gate_blocks_foreign_tenant_in_strict(strict_on):
    """Strict ON: same admin targeting a foreign tenant → 403."""
    import pytest as _pytest
    from fastapi import HTTPException

    from app.api.marketplace import _enforce_tenant_match

    with _pytest.raises(HTTPException) as exc:
        _enforce_tenant_match({"sub": "owner@acme-co.io"}, "victim-tenant")
    assert exc.value.status_code == 403


def test_gate_off_preserves_legacy_fail_open(strict_off):
    """Strict OFF (single-tenant default): a claim-less admin's foreign tenant
    is NOT blocked — legacy behaviour, no regression to the single-host flow."""
    from app.api.marketplace import _enforce_tenant_match

    _enforce_tenant_match({"sub": "owner@acme-co.io"}, "any-tenant")  # no raise


# --------------------------------------------------------------------------
# graph — raw Cypher surface is refused in strict mode
# --------------------------------------------------------------------------


@pytest.fixture()
def graph_admin():
    ctx = AuthContext(
        subject="admin@acme.local",
        tenant_id="tenant-a",
        roles=["admin"],
        raw_claims={"sub": "admin@acme.local"},
    )
    app.dependency_overrides[get_admin_or_bearer_auth_context] = lambda: ctx
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_admin_or_bearer_auth_context, None)


def test_strict_refuses_raw_cypher(
    client: TestClient, graph_admin, strict_on
) -> None:
    """A benign-looking scalar projection (`RETURN n.email AS e`) carries no
    tenant_id key and would slip past the row filter — strict mode refuses the
    whole raw surface before it reaches Neo4j (no live driver needed)."""
    r = client.post(
        "/v1/graph/cypher",
        json={"cypher": "MATCH (n) RETURN n.email AS e", "params": {}},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "raw_cypher_disabled_strict_mt"


def test_strict_refuses_nl_query(
    client: TestClient, graph_admin, strict_on
) -> None:
    r = client.post(
        "/v1/graph/nl-query",
        json={"intent": "list all customer emails", "locale": "en"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "raw_cypher_disabled_strict_mt"


def test_off_keeps_raw_cypher_reachable(
    client: TestClient, graph_admin, strict_off
) -> None:
    """Strict OFF: the raw endpoint is reachable again. With no live Neo4j it
    surfaces as 503/400 from the driver — the point is it is NOT the strict
    403, proving the gate is off."""
    r = client.post(
        "/v1/graph/cypher",
        json={"cypher": "MATCH (n) RETURN n LIMIT 1", "params": {}},
    )
    assert r.status_code != 403, r.text
