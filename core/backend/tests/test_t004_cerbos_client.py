"""T-004 — Cerbos client wrapper unit tests (no live PDP)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("cerbos")

from app.auth import cerbos_client as cc  # noqa: E402


def _fake_result(allowed_actions: set[str], all_actions: list[str]) -> SimpleNamespace:
    entry = SimpleNamespace(
        is_allowed=lambda action: action in allowed_actions,
    )
    return SimpleNamespace(
        results=[entry],
        failed=lambda: False,
        status_code=200,
    )


def _fake_failure() -> SimpleNamespace:
    return SimpleNamespace(
        results=[],
        failed=lambda: True,
        status_code=500,
    )


def test_build_principal_sets_tenant_attr() -> None:
    p = cc.build_principal("u1", roles=["member"], tenant_id="t1")
    assert p.id == "u1"
    assert "member" in p.roles
    assert p.attr["tenant_id"] == "t1"


def test_build_resource_sets_owner_and_tenant() -> None:
    r = cc.build_resource("proj-1", "project", tenant_id="t1", owner_id="u1")
    assert r.kind == "project"
    assert r.attr["owner_id"] == "u1"
    assert r.attr["tenant_id"] == "t1"


def test_is_allowed_returns_true_when_pdp_allows() -> None:
    pdp = MagicMock()
    pdp.check_resources.return_value = _fake_result({"read"}, ["read"])
    p = cc.build_principal("u", tenant_id="t1")
    r = cc.build_resource("p1", "project", tenant_id="t1", owner_id="u")

    assert cc.is_allowed(p, r, "read", client=pdp) is True


def test_is_allowed_returns_false_when_pdp_denies() -> None:
    pdp = MagicMock()
    pdp.check_resources.return_value = _fake_result(set(), ["update"])
    p = cc.build_principal("u", tenant_id="t1")
    r = cc.build_resource("p1", "project", tenant_id="t1")

    assert cc.is_allowed(p, r, "update", client=pdp) is False


def test_check_resources_returns_per_action_decisions() -> None:
    pdp = MagicMock()
    pdp.check_resources.return_value = _fake_result(
        {"read", "list"}, ["read", "list", "delete"]
    )
    p = cc.build_principal("u", tenant_id="t1")
    r = cc.build_resource("p1", "project", tenant_id="t1")

    decisions = cc.check_resources(p, r, ["read", "list", "delete"], client=pdp)
    assert decisions == {"read": True, "list": True, "delete": False}


def test_pdp_failure_treated_as_deny() -> None:
    pdp = MagicMock()
    pdp.check_resources.return_value = _fake_failure()
    p = cc.build_principal("u", tenant_id="t1")
    r = cc.build_resource("p1", "project", tenant_id="t1")

    decisions = cc.check_resources(p, r, ["read", "delete"], client=pdp)
    assert decisions == {"read": False, "delete": False}


def test_pdp_exception_treated_as_deny() -> None:
    pdp = MagicMock()
    pdp.check_resources.side_effect = RuntimeError("PDP unreachable")
    p = cc.build_principal("u", tenant_id="t1")
    r = cc.build_resource("p1", "project", tenant_id="t1")

    decisions = cc.check_resources(p, r, ["read"], client=pdp)
    assert decisions == {"read": False}
