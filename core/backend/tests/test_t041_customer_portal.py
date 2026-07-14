"""Customer portal account + project store tests."""

from __future__ import annotations

import pytest

from app.customer_portal_v10.account import (
    Account,
    AccountStore,
    PortalProjects,
)


def test_account_add_and_for_tenant_isolated() -> None:
    s = AccountStore()
    s.add(Account(account_id="1", tenant_id="t1", email="a@b.c", name="A"))
    s.add(Account(account_id="2", tenant_id="t2", email="x@y.z", name="X"))
    assert [a.email for a in s.for_tenant("t1")] == ["a@b.c"]


def test_invite_admin_only() -> None:
    s = AccountStore()
    with pytest.raises(PermissionError):
        s.invite(
            tenant_id="t1",
            email="a@b.c",
            role="member",
            invited_by_role="member",
        )
    inv = s.invite(
        tenant_id="t1",
        email="a@b.c",
        role="member",
        invited_by_role="admin",
    )
    assert inv.invite_id


def test_invite_revoke_and_pending() -> None:
    s = AccountStore()
    inv = s.invite(
        tenant_id="t1",
        email="a@b.c",
        role="admin",
        invited_by_role="owner",
    )
    assert s.pending_invites("t1")
    assert s.revoke(inv.invite_id) is True
    assert s.pending_invites("t1") == []


def test_project_create_archive_lifecycle() -> None:
    p = PortalProjects()
    proj = p.create(tenant_id="t1", name="Demo", owner_email="o@x.y")
    assert proj.project_id
    assert p.for_tenant("t1") == [proj]
    assert p.archive(project_id=proj.project_id, tenant_id="t1") is True
    assert p.for_tenant("t1") == []
    assert p.for_tenant("t1", include_archived=True)[0].archived is True


def test_project_archive_blocks_cross_tenant() -> None:
    p = PortalProjects()
    proj = p.create(tenant_id="t1", name="A", owner_email="o@x.y")
    assert p.archive(project_id=proj.project_id, tenant_id="t2") is False


def test_project_get_blocks_cross_tenant() -> None:
    p = PortalProjects()
    proj = p.create(tenant_id="t1", name="A", owner_email="o@x.y")
    assert p.get(project_id=proj.project_id, tenant_id="t1") is not None
    assert p.get(project_id=proj.project_id, tenant_id="t2") is None
