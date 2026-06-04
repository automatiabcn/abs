# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""PATCH /v1/admin/users/{id} — role/status mutation + last-admin guard."""

from __future__ import annotations

import bcrypt
import pytest

from app.config import settings


def _admin_token(client, monkeypatch) -> str:
    monkeypatch.setattr(
        settings,
        "admin_password_hash",
        bcrypt.hashpw(b"s3cret", bcrypt.gensalt()).decode("utf-8"),
    )
    r = client.post("/v1/admin/login", json={"password": "s3cret"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(autouse=True)
def _reset_admin_state():
    from app.api.admin import auth as a

    a._reset_state_for_tests()
    yield
    a._reset_state_for_tests()


def _seed(email: str, role: str, status: str, tenant: str) -> int:
    from sqlmodel import Session

    from app.db.models import User
    from app.db.session import get_engine

    with Session(get_engine()) as s:
        u = User(
            email=email,
            password_hash="x",
            tenant_slug=tenant,
            role=role,
            status=status,
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        return int(u.id)


def _clean(tenant: str) -> None:
    from sqlmodel import Session, delete

    from app.db.models import User
    from app.db.session import get_engine

    with Session(get_engine()) as s:
        s.execute(delete(User).where(User.tenant_slug == tenant))
        s.commit()


def test_demote_then_last_admin_protected(client, monkeypatch):
    import app.api.admin.users as users_mod

    tenant = "rbac-test"
    monkeypatch.setattr(users_mod, "_resolve_tenant", lambda admin: tenant)
    token = _admin_token(client, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}

    _clean(tenant)
    a1 = _seed("admin1@rbac.test", "admin", "active", tenant)
    a2 = _seed("admin2@rbac.test", "admin", "active", tenant)

    # Two active admins → demoting one is allowed.
    r = client.patch(
        f"/v1/admin/users/{a2}", headers=headers, json={"role": "member"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "member"

    # a1 is now the only active admin → revoking it must be blocked.
    r2 = client.patch(
        f"/v1/admin/users/{a1}", headers=headers, json={"status": "revoked"}
    )
    assert r2.status_code == 409, r2.text
    detail = r2.json()["detail"]
    err = detail.get("error") if isinstance(detail, dict) else detail
    assert err == "last_admin_protected"

    _clean(tenant)


def test_promote_member_to_admin(client, monkeypatch):
    import app.api.admin.users as users_mod

    tenant = "rbac-promote"
    monkeypatch.setattr(users_mod, "_resolve_tenant", lambda admin: tenant)
    token = _admin_token(client, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}

    _clean(tenant)
    _seed("owner@rbac.test", "admin", "active", tenant)
    member = _seed("member@rbac.test", "member", "active", tenant)

    r = client.patch(
        f"/v1/admin/users/{member}", headers=headers, json={"role": "admin"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"
    _clean(tenant)


def test_update_requires_admin(client):
    r = client.patch("/v1/admin/users/1", json={"role": "member"})
    assert r.status_code == 401


def test_cross_tenant_update_404(client, monkeypatch):
    import app.api.admin.users as users_mod

    monkeypatch.setattr(users_mod, "_resolve_tenant", lambda admin: "tenant-a")
    token = _admin_token(client, monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}

    other = _seed("foreign@rbac.test", "member", "active", "tenant-b")
    r = client.patch(
        f"/v1/admin/users/{other}", headers=headers, json={"role": "admin"}
    )
    assert r.status_code == 404, r.text
    _clean("tenant-b")
