"""MT Phase 1 — project CRUD + membership endpoints + RBAC."""

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


def test_projects_require_admin(client):
    assert client.get("/v1/admin/projects").status_code in (401, 403)
    assert client.post("/v1/admin/projects", json={"slug": "x"}).status_code in (
        401,
        403,
    )


def test_create_list_archive_project(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}

    r = client.post(
        "/v1/admin/projects",
        headers=h,
        json={"slug": "islam-felsefesi", "name": "İslam Felsefesi"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "islam-felsefesi"

    lr = client.get("/v1/admin/projects", headers=h)
    assert lr.status_code == 200
    slugs = [p["slug"] for p in lr.json()["projects"]]
    assert "islam-felsefesi" in slugs

    ar = client.delete("/v1/admin/projects/islam-felsefesi", headers=h)
    assert ar.status_code == 200 and ar.json()["archived"] is True

    # archived → no longer listed
    lr2 = client.get("/v1/admin/projects", headers=h)
    assert "islam-felsefesi" not in [p["slug"] for p in lr2.json()["projects"]]


def test_duplicate_slug_rejected(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    client.post("/v1/admin/projects", headers=h, json={"slug": "dup-proj"})
    r = client.post("/v1/admin/projects", headers=h, json={"slug": "dup-proj"})
    assert r.status_code == 409


def test_invalid_slug_rejected(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/projects",
        headers={"Authorization": f"Bearer {tok}"},
        json={"slug": "Bad Slug!"},
    )
    assert r.status_code == 422


def test_creator_becomes_owner_and_membership_crud(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    client.post("/v1/admin/projects", headers=h, json={"slug": "erken-hristiyanlik"})

    # creator is auto-added as owner
    mr = client.get("/v1/admin/projects/erken-hristiyanlik/members", headers=h)
    assert mr.status_code == 200
    owners = [m for m in mr.json()["members"] if m["role"] == "owner"]
    assert owners, mr.text

    # add an editor
    ar = client.post(
        "/v1/admin/projects/erken-hristiyanlik/members",
        headers=h,
        json={"user_subject": "ayse@x.com", "role": "editor"},
    )
    assert ar.status_code == 200
    members = client.get(
        "/v1/admin/projects/erken-hristiyanlik/members", headers=h
    ).json()["members"]
    assert any(
        m["user_subject"] == "ayse@x.com" and m["role"] == "editor" for m in members
    )

    # remove
    dr = client.delete(
        "/v1/admin/projects/erken-hristiyanlik/members/ayse@x.com", headers=h
    )
    assert dr.status_code == 200 and dr.json()["removed"] is True


def test_add_member_unknown_project_404(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    r = client.post(
        "/v1/admin/projects/ghost/members",
        headers={"Authorization": f"Bearer {tok}"},
        json={"user_subject": "a@x.com", "role": "viewer"},
    )
    assert r.status_code == 404


def test_invalid_role_rejected(client, monkeypatch):
    tok = _admin_token(client, monkeypatch)
    h = {"Authorization": f"Bearer {tok}"}
    client.post("/v1/admin/projects", headers=h, json={"slug": "role-test"})
    r = client.post(
        "/v1/admin/projects/role-test/members",
        headers=h,
        json={"user_subject": "a@x.com", "role": "boss"},
    )
    assert r.status_code == 422
