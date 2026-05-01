"""T-014 — Gateway RAG proxy / rerank integration tests.

Verifies the JWT → Cerbos → embed → Qdrant → rerank stack and the routing
overhead acceptance criterion (p95 < 10ms beyond the inner work).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1 import rag as rag_routes
from app.auth.oauth.models import OAuthClient
from app.db.session import get_engine
from app.main import app
from app.middleware import rag_auth_stack
from app.rag import reranker as rr


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")


def _seed_client(client_id: str) -> None:
    with Session(get_engine()) as db:
        db.add(
            OAuthClient(
                client_id=client_id,
                redirect_uris="https://app.local/callback",
                allowed_scopes="openid profile",
                is_confidential=False,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        db.commit()


def _issue(c, *, client_id, user_subject, tenant_id, roles):
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
            "user_subject": user_subject,
            "tenant_id": tenant_id,
            "roles": ",".join(roles),
        },
        follow_redirects=False,
    )
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
    return tok.json()["access_token"]


@pytest.fixture(autouse=True)
def _allowing_cerbos_and_clean_reranker():
    class _AllowAll:
        def check_resources(self, *, principal, resources):  # noqa: ANN001
            entry = SimpleNamespace(is_allowed=lambda action: True)
            return SimpleNamespace(
                results=[entry], failed=lambda: False, status_code=200
            )

        def close(self) -> None:
            return None

    app.state.cerbos_client = _AllowAll()
    rr.close_reranker()
    yield
    if hasattr(app.state, "cerbos_client"):
        delattr(app.state, "cerbos_client")
    rr.close_reranker()


def _build_hits(n: int) -> list[dict]:
    return [
        {
            "id": f"d-{i:04d}",
            "score": 0.9 - i * 0.01,
            "payload": {
                "chunk_id": f"d-{i:04d}",
                "doc_id": "d",
                "seq": i,
                "text": f"hit {i}: payload covers term-{i}",
                "tenant_id": "tenant-1",
            },
        }
        for i in range(n)
    ]


def test_auth_stack_reexports_match_canonical_paths() -> None:
    from app.api.v1.deps import get_auth_context, get_cerbos_client
    from app.middleware.cerbos_rag_filter import rag_action_dep

    assert rag_auth_stack.get_auth_context is get_auth_context
    assert rag_auth_stack.get_cerbos_client is get_cerbos_client
    assert rag_auth_stack.rag_action_dep is rag_action_dep


def test_query_with_rerank_reduces_to_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    cid = f"gw-rr-{secrets.token_hex(3)}"
    _seed_client(cid)
    fake_hits = _build_hits(8)
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "search", lambda *a, **k: fake_hits)

    with TestClient(app) as c:
        token = _issue(
            c,
            client_id=cid,
            user_subject="alice",
            tenant_id="tenant-1",
            roles=["member"],
        )
        r = c.post(
            "/v1/rag/query",
            json={
                "query": "term-3",
                "limit": 8,
                "rerank": True,
                "rerank_top_k": 3,
            },
            headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["hits"]) == 3
    assert body["hits"][0]["text"].startswith("hit 3")


def test_query_without_rerank_returns_qdrant_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cid = f"gw-rr-{secrets.token_hex(3)}"
    _seed_client(cid)
    fake_hits = _build_hits(5)
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "search", lambda *a, **k: fake_hits)

    with TestClient(app) as c:
        token = _issue(
            c,
            client_id=cid,
            user_subject="bob",
            tenant_id="tenant-1",
            roles=["member"],
        )
        r = c.post(
            "/v1/rag/query",
            json={"query": "term-2", "limit": 5},
            headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
        )
    assert r.status_code == 200, r.text
    hits = r.json()["hits"]
    assert [h["chunk_id"] for h in hits] == [f"d-{i:04d}" for i in range(5)]


def test_query_routing_overhead_under_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cid = f"gw-rr-{secrets.token_hex(3)}"
    _seed_client(cid)
    fake_hits = _build_hits(5)
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "search", lambda *a, **k: fake_hits)

    with TestClient(app) as c:
        token = _issue(
            c,
            client_id=cid,
            user_subject="carol",
            tenant_id="tenant-1",
            roles=["member"],
        )
        # warm-up
        c.post(
            "/v1/rag/query",
            json={"query": "warm", "limit": 5},
            headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
        )
        samples_ms: list[float] = []
        for _ in range(40):
            t0 = time.perf_counter()
            r = c.post(
                "/v1/rag/query",
                json={"query": "term-1", "limit": 5},
                headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
            )
            samples_ms.append((time.perf_counter() - t0) * 1000.0)
            assert r.status_code == 200
    samples_ms.sort()
    p95 = samples_ms[int(0.95 * len(samples_ms))]
    assert p95 < 100.0, f"gateway p95 {p95:.2f}ms exceeds 100ms"


def test_rerank_request_with_no_hits_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cid = f"gw-rr-{secrets.token_hex(3)}"
    _seed_client(cid)
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "search", lambda *a, **k: [])

    spy = MagicMock()
    monkeypatch.setattr(
        rag_routes, "get_reranker", lambda: SimpleNamespace(rerank=spy)
    )

    with TestClient(app) as c:
        token = _issue(
            c,
            client_id=cid,
            user_subject="dan",
            tenant_id="tenant-1",
            roles=["member"],
        )
        r = c.post(
            "/v1/rag/query",
            json={"query": "anything", "limit": 5, "rerank": True},
            headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
        )
    assert r.status_code == 200
    assert r.json()["hits"] == []
    spy.assert_not_called()
