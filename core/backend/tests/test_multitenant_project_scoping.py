"""MT Phase 1 (B4) — active-project resolution + per-project RAG scoping."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1 import rag as rag_routes
from app.auth.oauth.models import OAuthClient
from app.db.session import get_engine
from app.db.tenant_models import Project
from app.main import app
from app.multitenant import project_members as pm


# ── resolver unit tests ─────────────────────────────────────────────────────


def _seed_project(slug: str, tenant: str) -> None:
    with Session(get_engine()) as db:
        if not db.get(Project, slug):
            db.add(
                Project(
                    slug=slug,
                    tenant_slug=tenant,
                    name=slug,
                    owner_subject="o@x.com",
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()


def _req(project_id: str | None):
    headers = {}
    if project_id is not None:
        headers["X-Project-Id"] = project_id
    return SimpleNamespace(headers=headers)


def test_no_header_returns_none():
    from app.api.v1.project_context import resolve_active_project

    assert (
        resolve_active_project(_req(None), tenant_slug="t", subject="u", roles=[])
        is None
    )


def test_unknown_project_404():
    from fastapi import HTTPException

    from app.api.v1.project_context import resolve_active_project

    with pytest.raises(HTTPException) as e:
        resolve_active_project(
            _req("ghost-proj"), tenant_slug="t-b4", subject="u", roles=[]
        )
    assert e.value.status_code == 404


def test_non_member_403():
    from fastapi import HTTPException

    from app.api.v1.project_context import resolve_active_project

    _seed_project("b4-secret", "t-b4")
    with pytest.raises(HTTPException) as e:
        resolve_active_project(
            _req("b4-secret"),
            tenant_slug="t-b4",
            subject="outsider@x.com",
            roles=["member"],
        )
    assert e.value.status_code == 403


def test_member_allowed():
    from app.api.v1.project_context import resolve_active_project

    _seed_project("b4-open", "t-b4")
    pm.add_member(tenant_slug="t-b4", project_slug="b4-open", user_subject="m@x.com")
    got = resolve_active_project(
        _req("b4-open"), tenant_slug="t-b4", subject="m@x.com", roles=["member"]
    )
    assert got == "b4-open"


def test_admin_bypasses_membership():
    from app.api.v1.project_context import resolve_active_project

    _seed_project("b4-adminonly", "t-b4")
    got = resolve_active_project(
        _req("b4-adminonly"), tenant_slug="t-b4", subject="boss@x.com", roles=["admin"]
    )
    assert got == "b4-adminonly"


# ── ingest payload + query filter ────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _fake_cerbos():
    class _C:
        def check_resources(self, *, principal, resources):  # noqa: ANN001
            return SimpleNamespace(
                results=[SimpleNamespace(is_allowed=lambda a: True)],
                failed=lambda: False,
                status_code=200,
            )

        def close(self):
            return None

    app.state.cerbos_client = _C()
    yield
    if hasattr(app.state, "cerbos_client"):
        delattr(app.state, "cerbos_client")


def _headers(c, *, cid, tenant, project=None):
    v = "v" * 64
    chal = (
        base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    with Session(get_engine()) as db:
        db.add(
            OAuthClient(
                client_id=cid,
                redirect_uris="https://a/cb",
                allowed_scopes="openid",
                is_confidential=False,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        db.commit()
    a = c.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://a/cb",
            "code_challenge": chal,
            "code_challenge_method": "S256",
            "scope": "rag:query",
            "user_subject": "admin@x.com",
            "tenant_id": tenant,
            "roles": "admin",
        },
        follow_redirects=False,
    )
    code = a.headers["location"].split("code=", 1)[1].split("&", 1)[0]
    tok = c.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": cid,
            "code": code,
            "redirect_uri": "https://a/cb",
            "code_verifier": v,
        },
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}", "X-ABS-Audience": cid}
    if project:
        h["X-Project-Id"] = project
    return h


def test_query_adds_project_filter(monkeypatch):
    cid = f"b4-{secrets.token_hex(3)}"
    _seed_project("proj-q", "t-q")
    captured = {}

    def fake_search(
        *,
        collection,
        tenant_id,
        query_vector,
        limit,
        score_threshold=None,
        extra_filter=None,
    ):
        captured["filter"] = extra_filter
        return []

    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "search", fake_search)
    with TestClient(app) as c:
        h = _headers(c, cid=cid, tenant="t-q", project="proj-q")
        r = c.post("/v1/rag/query", json={"query": "x"}, headers=h)
    assert r.status_code == 200, r.text
    f = captured["filter"]
    assert f is not None
    keys = [getattr(cond, "key", None) for cond in f.must]
    assert "project_id" in keys


def test_ingest_stamps_project_id(monkeypatch):
    cid = f"b4i-{secrets.token_hex(3)}"
    _seed_project("proj-i", "t-i")
    captured = {}

    def fake_upsert(*, collection, tenant_id, points):
        captured["payload0"] = points[0].payload
        return len(points)

    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "upsert_points", fake_upsert)
    with TestClient(app) as c:
        h = _headers(c, cid=cid, tenant="t-i", project="proj-i")
        r = c.post("/v1/rag/ingest", json={"text": "hello world. " * 50}, headers=h)
    assert r.status_code == 200, r.text
    assert captured["payload0"].get("project_id") == "proj-i"


def test_ingest_without_project_omits_project_id(monkeypatch):
    cid = f"b4n-{secrets.token_hex(3)}"
    captured = {}

    def fake_upsert(*, collection, tenant_id, points):
        captured["payload0"] = points[0].payload
        return len(points)

    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "upsert_points", fake_upsert)
    with TestClient(app) as c:
        h = _headers(c, cid=cid, tenant="t-n")  # no project header
        r = c.post("/v1/rag/ingest", json={"text": "hello world. " * 50}, headers=h)
    assert r.status_code == 200, r.text
    assert "project_id" not in captured["payload0"]
