# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Multi-tenant Faz0 #3 — claiming a self-signup provisions a real workspace.

Before this, ``/auth/signup`` → claim only flipped the User row to active; the
session carried a ``tenant_slug`` that pointed at nothing. Now the claim
idempotently bootstraps Tenant + default Project + owner membership so the new
signer-upper lands on a working tenant.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.db.session import get_engine
from app.db.tenant_models import Project, Tenant, TenantProject
from app.multitenant import project_members as pm
from app.multitenant.provisioning import ensure_tenant_provisioned


def test_ensure_tenant_provisioned_is_idempotent():
    slug = "prov-unit-co"
    first = ensure_tenant_provisioned(slug, owner_subject="owner@prov-unit-co.io")
    assert first["created_tenant"] is True
    assert first["created_project"] is True

    # Second call must not duplicate anything.
    second = ensure_tenant_provisioned(slug, owner_subject="owner@prov-unit-co.io")
    assert second["created_tenant"] is False
    assert second["created_project"] is False

    with Session(get_engine()) as db:
        tenants = db.exec(select(Tenant).where(Tenant.slug == slug)).all()
        assert len(tenants) == 1
        projects = db.exec(
            select(Project).where(
                Project.tenant_slug == slug, Project.slug == "default"
            )
        ).all()
        assert len(projects) == 1
        assert projects[0].qdrant_collection == "abs_documents"
        links = db.exec(
            select(TenantProject).where(
                TenantProject.tenant_slug == slug,
                TenantProject.project_slug == "default",
                TenantProject.revoked_at.is_(None),  # type: ignore[union-attr]
            )
        ).all()
        assert len(links) == 1

    # Owner is a project member with the owner role.
    role = pm.get_role(
        tenant_slug=slug,
        project_slug="default",
        user_subject="owner@prov-unit-co.io",
    )
    assert role == pm.ROLE_OWNER


def test_provisioned_default_for_single_tenant_is_harmless():
    """Calling it for "default" only makes the canonical rows exist — additive,
    no error, idempotent (single-tenant self-host stays valid)."""
    out = ensure_tenant_provisioned("default", owner_subject="admin@local")
    assert out["tenant"] == "default"
    with Session(get_engine()) as db:
        t = db.exec(select(Tenant).where(Tenant.slug == "default")).first()
        assert t is not None


def test_signup_claim_provisions_tenant(client):
    """End-to-end: dev-mode signup returns the /activate magic link; claiming it
    flips the user active AND provisions their tenant workspace."""
    slug = "prov-e2e-co"
    r = client.post(
        "/auth/signup",
        json={"email": "founder@prov-e2e-co.io", "tenant_slug": slug},
    )
    assert r.status_code == 201, r.text
    link = r.json().get("magic_link", "")
    assert "token=" in link, r.json()
    token = link.split("token=", 1)[1]

    rc = client.get(f"/auth/magic?token={token}")
    assert rc.status_code == 200, rc.text
    assert rc.json().get("tenant_slug") == slug

    with Session(get_engine()) as db:
        tenant = db.exec(select(Tenant).where(Tenant.slug == slug)).first()
        assert tenant is not None, "tenant row was not provisioned on claim"
        project = db.exec(
            select(Project).where(
                Project.tenant_slug == slug, Project.slug == "default"
            )
        ).first()
        assert project is not None, "default project was not provisioned"
        assert project.owner_subject == "founder@prov-e2e-co.io"
