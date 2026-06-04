# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Multi-admin RBAC — an active users-table role==admin row reaches /v1/admin/*
via its panel session; member/viewer and self-signup users do not."""

from __future__ import annotations

import bcrypt


def _seed(email: str, role: str, status: str, pw: str = "pw12345!") -> str:
    from sqlmodel import Session

    from app.db.models import User
    from app.db.session import get_engine

    h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    with Session(get_engine()) as s:
        s.add(
            User(
                email=email,
                password_hash=h,
                tenant_slug="default",
                role=role,
                status=status,
            )
        )
        s.commit()
    return pw


def test_active_admin_user_reaches_admin_api(client):
    pw = _seed("multiadmin@demo.local", "admin", "active")
    r = client.post(
        "/auth/login",
        json={"email": "multiadmin@demo.local", "password": pw},
    )
    assert r.status_code == 200, r.text
    # Panel-session cookie is now set; the admin endpoint must accept it
    # because the users row is role=admin + active (multi-admin grant).
    r2 = client.get("/v1/admin/users")
    assert r2.status_code == 200, r2.text


def test_member_user_blocked_from_admin_api(client):
    pw = _seed("plainmember@demo.local", "member", "active")
    r = client.post(
        "/auth/login",
        json={"email": "plainmember@demo.local", "password": pw},
    )
    assert r.status_code == 200, r.text
    r2 = client.get("/v1/admin/users")
    assert r2.status_code == 401, r2.text


def test_viewer_user_blocked_from_admin_api(client):
    pw = _seed("plainviewer@demo.local", "viewer", "active")
    client.post(
        "/auth/login",
        json={"email": "plainviewer@demo.local", "password": pw},
    )
    r2 = client.get("/v1/admin/users")
    assert r2.status_code == 401, r2.text


def test_signup_creates_member_not_admin(client):
    """Escalation guard — public self-signup must mint role=member, otherwise
    the multi-admin grant above would let anyone self-promote."""
    r = client.post(
        "/auth/signup",
        json={
            "email": "freshsignup@demo.local",
            "tenant_slug": "default",
            "password": "S3cret-Password!1",
        },
    )
    assert r.status_code in (200, 201), r.text

    from sqlmodel import Session, select

    from app.db.models import User
    from app.db.session import get_engine

    with Session(get_engine()) as s:
        u = s.exec(
            select(User).where(User.email == "freshsignup@demo.local")
        ).first()
        assert u is not None
        assert u.role == "member", f"signup role must be member, got {u.role}"
