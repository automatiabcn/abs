"""GraphRAG — /v1/graph-rag route tests (auth, enable-gate, degrade paths)."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api import graph_rag as gr_routes
from app.auth.oauth.models import OAuthClient
from app.config import settings
from app.db.session import get_engine
from app.graph_rag import retrieve as rt
from app.main import app


@pytest.fixture(autouse=True)
def _install_fake_cerbos():
    class _AllowingCerbos:
        def check_resources(self, *, principal, resources):  # noqa: ANN001
            entry = SimpleNamespace(is_allowed=lambda action: True)
            return SimpleNamespace(
                results=[entry], failed=lambda: False, status_code=200
            )

        def close(self) -> None:
            return None

    app.state.cerbos_client = _AllowingCerbos()
    yield
    if hasattr(app.state, "cerbos_client"):
        delattr(app.state, "cerbos_client")


@pytest.fixture(autouse=True)
def _enable_graphrag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "graphrag_enabled", True, raising=False)
    yield


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def _seed_client(client_id: str) -> None:
    from sqlalchemy.exc import IntegrityError

    with Session(get_engine()) as db:
        existing = db.exec(
            __import__("sqlmodel")
            .select(OAuthClient)
            .where(OAuthClient.client_id == client_id)
        ).first()
        if existing:
            return
        db.add(
            OAuthClient(
                client_id=client_id,
                redirect_uris="https://app.local/callback",
                allowed_scopes="openid profile",
                is_confidential=False,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


_CLIENT_ID = "graphrag-test-client"


def _auth_headers(
    c: TestClient, *, tenant_id: str, subject: str = "u1"
) -> dict[str, str]:
    tok = _token(c, tenant_id=tenant_id, subject=subject)
    return {"Authorization": f"Bearer {tok}", "X-ABS-Audience": _CLIENT_ID}


def _token(c: TestClient, *, tenant_id: str, subject: str = "u1") -> str:
    client_id = _CLIENT_ID
    _seed_client(client_id)
    verifier = "v" * 64
    auth = c.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://app.local/callback",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "scope": "rag:query",
            "user_subject": subject,
            "tenant_id": tenant_id,
            "roles": "admin",
        },
        follow_redirects=False,
    )
    assert auth.status_code == 302, auth.text
    code = auth.headers["location"].split("code=", 1)[1].split("&", 1)[0]
    tok = c.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": "https://app.local/callback",
            "code_verifier": verifier,
        },
    )
    assert tok.status_code == 200, tok.text
    return tok.json()["access_token"]


def test_query_requires_auth() -> None:
    with TestClient(app) as c:
        r = c.post("/v1/graph-rag/query", json={"query": "x"})
    assert r.status_code in (401, 403)


def test_routes_404_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "graphrag_enabled", False, raising=False)
    with TestClient(app) as c:
        h = _auth_headers(c, tenant_id="t1")
        rq = c.post("/v1/graph-rag/query", json={"query": "x"}, headers=h)
        rb = c.post("/v1/graph-rag/build", json={}, headers=h)
    assert rq.status_code == 404
    assert rq.json()["detail"] == "graphrag_disabled"
    assert rb.status_code == 404


def test_build_422_when_no_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gr_routes, "settings", settings, raising=False)
    import app.providers.cascade as casc

    monkeypatch.setattr(casc, "get_active_providers", lambda *a, **k: [])
    with TestClient(app) as c:
        r = c.post(
            "/v1/graph-rag/build",
            json={},
            headers=_auth_headers(c, tenant_id="t1"),
        )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "no_providers_configured"


def test_query_returns_answer_and_subgraph(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.graph_rag.retrieve import GraphCitation, GraphRagResult

    async def _fake_query(query, *, tenant_id, top_k, synthesize, depth=1):
        assert tenant_id == "tenantA"
        return GraphRagResult(
            answer="cevap [1]",
            citations=[
                GraphCitation(
                    chunk_id="c1",
                    source="rapor.pdf",
                    excerpt="...",
                    score=0.7,
                    doc_id="d1",
                )
            ],
            entities=[{"id": "person:ahmet", "name": "Ahmet", "type": "Person"}],
            relations=[],
            used_graph=True,
        )

    monkeypatch.setattr(rt, "graph_rag_query", _fake_query)
    with TestClient(app) as c:
        r = c.post(
            "/v1/graph-rag/query",
            json={"query": "Ahmet kim?", "limit": 5},
            headers=_auth_headers(c, tenant_id="tenantA"),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "cevap [1]"
    assert body["citations"][0]["source"] == "rapor.pdf"
    assert body["entities"][0]["id"] == "person:ahmet"
    assert body["used_graph"] is True


def test_query_validation_rejects_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as c:
        r = c.post(
            "/v1/graph-rag/query",
            json={"query": ""},
            headers=_auth_headers(c, tenant_id="t1"),
        )
    assert r.status_code == 422  # pydantic min_length
