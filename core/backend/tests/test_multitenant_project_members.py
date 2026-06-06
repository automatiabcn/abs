"""Multi-tenant Phase 1 — N-N user↔project membership store."""

from __future__ import annotations

import pytest

from app.multitenant import project_members as pm


def test_add_and_get_role() -> None:
    pm.add_member(
        tenant_slug="t1", project_slug="p1", user_subject="a@x.com",
        role=pm.ROLE_EDITOR,
    )
    assert pm.get_role(
        tenant_slug="t1", project_slug="p1", user_subject="a@x.com"
    ) == "editor"


def test_user_in_multiple_projects() -> None:
    pm.add_member(tenant_slug="t2", project_slug="alpha", user_subject="u@x.com")
    pm.add_member(
        tenant_slug="t2", project_slug="beta", user_subject="u@x.com",
        role=pm.ROLE_OWNER,
    )
    projects = pm.list_projects_for_user(tenant_slug="t2", user_subject="u@x.com")
    slugs = {p["project_slug"] for p in projects}
    assert slugs == {"alpha", "beta"}


def test_add_is_idempotent_and_updates_role() -> None:
    pm.add_member(
        tenant_slug="t3", project_slug="p", user_subject="a@x.com",
        role=pm.ROLE_VIEWER,
    )
    pm.add_member(
        tenant_slug="t3", project_slug="p", user_subject="a@x.com",
        role=pm.ROLE_OWNER,
    )
    members = pm.list_members_for_project(tenant_slug="t3", project_slug="p")
    assert len(members) == 1
    assert members[0]["role"] == "owner"


def test_remove_member_soft_revokes() -> None:
    pm.add_member(tenant_slug="t4", project_slug="p", user_subject="a@x.com")
    assert pm.remove_member(
        tenant_slug="t4", project_slug="p", user_subject="a@x.com"
    ) is True
    assert pm.get_role(
        tenant_slug="t4", project_slug="p", user_subject="a@x.com"
    ) is None
    # Removing again is a no-op (already revoked).
    assert pm.remove_member(
        tenant_slug="t4", project_slug="p", user_subject="a@x.com"
    ) is False


def test_readd_after_revoke_reactivates() -> None:
    pm.add_member(tenant_slug="t5", project_slug="p", user_subject="a@x.com")
    pm.remove_member(tenant_slug="t5", project_slug="p", user_subject="a@x.com")
    pm.add_member(
        tenant_slug="t5", project_slug="p", user_subject="a@x.com",
        role=pm.ROLE_EDITOR,
    )
    assert pm.get_role(
        tenant_slug="t5", project_slug="p", user_subject="a@x.com"
    ) == "editor"


def test_tenant_isolation_membership() -> None:
    pm.add_member(tenant_slug="tA", project_slug="shared", user_subject="a@x.com")
    # Same project slug + user under a different tenant → not a member.
    assert pm.get_role(
        tenant_slug="tB", project_slug="shared", user_subject="a@x.com"
    ) is None


def test_invalid_role_rejected() -> None:
    with pytest.raises(ValueError):
        pm.add_member(
            tenant_slug="t", project_slug="p", user_subject="a@x.com", role="boss"
        )


def test_missing_fields_rejected() -> None:
    with pytest.raises(ValueError):
        pm.add_member(tenant_slug="", project_slug="p", user_subject="a@x.com")
