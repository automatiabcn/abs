"""MT hardening — project slug is unique PER TENANT + archived slug reuse."""

from __future__ import annotations

from datetime import datetime, timezone

import bcrypt
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.config import settings
from app.db.session import get_engine
from app.db.tenant_models import Project


# ── schema: composite (tenant_slug, slug) unique ────────────────────────────


def test_same_slug_different_tenants_ok():
    with Session(get_engine()) as db:
        for t in ("tenantA", "tenantB"):
            db.add(Project(slug="shared-proj", tenant_slug=t, name="x",
                           created_at=datetime.now(timezone.utc)))
        db.commit()
        rows = db.exec(select(Project).where(Project.slug == "shared-proj")).all()
        assert {r.tenant_slug for r in rows} >= {"tenantA", "tenantB"}


def test_same_slug_same_tenant_conflicts():
    with Session(get_engine()) as db:
        db.add(Project(slug="dup-one", tenant_slug="tdup", name="a",
                       created_at=datetime.now(timezone.utc)))
        db.commit()
    with Session(get_engine()) as db:
        db.add(Project(slug="dup-one", tenant_slug="tdup", name="b",
                       created_at=datetime.now(timezone.utc)))
        with pytest.raises(IntegrityError):
            db.commit()


# ── route: archived slug reactivation ───────────────────────────────────────


def _admin_token(client, monkeypatch) -> str:
    monkeypatch.setattr(
        settings, "admin_password_hash",
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


def test_recreate_after_archive_reactivates(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/v1/admin/projects", headers=h,
                       json={"slug": "reuse-me", "name": "First"}).status_code == 200
    assert client.delete("/v1/admin/projects/reuse-me", headers=h).status_code == 200
    # recreate the same slug → reactivated, NOT 409
    r = client.post("/v1/admin/projects", headers=h,
                    json={"slug": "reuse-me", "name": "Second"})
    assert r.status_code == 200, r.text
    listed = client.get("/v1/admin/projects", headers=h).json()["projects"]
    match = [p for p in listed if p["slug"] == "reuse-me"]
    assert match and match[0]["name"] == "Second"


def test_active_duplicate_still_409(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    client.post("/v1/admin/projects", headers=h, json={"slug": "live-dup"})
    r = client.post("/v1/admin/projects", headers=h, json={"slug": "live-dup"})
    assert r.status_code == 409
