"""Cerbos PDP live integration test.

Skipped unless ABS_CERBOS_HOST points at a reachable Cerbos PDP. Run via:

    docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d cerbos
    pytest tests/integration/test_t004_cerbos_live.py -v

Acceptance: cross-tenant access returns DENY (multi-tenant isolation gate).
"""

from __future__ import annotations

import os

import httpx
import pytest

pytest.importorskip("cerbos")

from app.auth.cerbos_client import build_principal, build_resource, is_allowed  # noqa: E402
from app.config import settings  # noqa: E402

CERBOS_URL = os.environ.get("ABS_CERBOS_HOST", "http://127.0.0.1:3592")


def _broker_reachable() -> bool:
    try:
        r = httpx.get(f"{CERBOS_URL}/_cerbos/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def _require_pdp(monkeypatch_module=None):
    if not _broker_reachable():
        pytest.skip(f"Cerbos PDP not reachable at {CERBOS_URL}")
    settings.cerbos_host = CERBOS_URL
    yield


def test_owner_can_update_own_project_in_own_tenant() -> None:
    p = build_principal("alice", roles=["member"], tenant_id="t1")
    r = build_resource("proj-1", "project", tenant_id="t1", owner_id="alice")
    assert is_allowed(p, r, "update") is True


def test_member_cannot_update_someone_elses_project() -> None:
    p = build_principal("alice", roles=["member"], tenant_id="t1")
    r = build_resource("proj-2", "project", tenant_id="t1", owner_id="bob")
    assert is_allowed(p, r, "update") is False


def test_cross_tenant_read_denied() -> None:
    p = build_principal("alice", roles=["member"], tenant_id="t1")
    r = build_resource("proj-x", "project", tenant_id="t2", owner_id="alice")
    assert is_allowed(p, r, "read") is False


def test_admin_can_delete_any_project_in_their_tenant() -> None:
    p = build_principal("bob", roles=["admin"], tenant_id="t1")
    r = build_resource("proj-3", "project", tenant_id="t1", owner_id="alice")
    assert is_allowed(p, r, "delete") is True


def test_admin_cannot_delete_other_tenant_project() -> None:
    p = build_principal("bob", roles=["admin"], tenant_id="t1")
    r = build_resource("proj-4", "project", tenant_id="t2", owner_id="alice")
    assert is_allowed(p, r, "delete") is False


def test_suspended_principal_blocked_everywhere() -> None:
    p = build_principal(
        "dan",
        roles=["admin"],
        tenant_id="t1",
        extra_attrs={"suspended": True},
    )
    r = build_resource("proj-5", "project", tenant_id="t1", owner_id="dan")
    assert is_allowed(p, r, "read") is False
    assert is_allowed(p, r, "update") is False
    assert is_allowed(p, r, "delete") is False
