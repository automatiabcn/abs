"""Q12 Founder Tester Round 2 (BUG-6) — `/v1/rag/*` cookie-session fallback.

`/admin/rag` is an operator console served behind the panel admin cookie
session (`abs_session`). Before this round it could not call `/v1/rag/ingest`
or `/v1/rag/query` because those endpoints required a Bearer JWT — a token
the cookie session never carries. The fix adds a cookie-session fallback to
`get_auth_context`: when no Bearer header is present, the dep accepts the
admin cookie and synthesises an `AuthContext` carrying the admin's resolved
tenant + `roles=["admin"]`.

Tests:
1. Cookie session + no Bearer → 200 on `/v1/rag/query` (cerbos ALLOW fixture).
2. No cookie + no Bearer → 401 missing_bearer_token (regression guard).
3. Cookie session + valid Bearer → Bearer wins (multi-tenant clients keep
   their JWT-claim semantics).
4. `/v1/rag/ingest` POST via cookie session → 200.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import rag as rag_routes
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


@pytest.fixture
def fake_qdrant(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Stub the Qdrant search to keep the test hermetic — we are testing
    the auth surface, not vector retrieval."""
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(
        rag_routes.qc, "search", lambda **k: []
    )
    monkeypatch.setattr(rag_routes.qc, "upsert_points", lambda **k: 1)

    embedder = MagicMock()
    embedder.dim = 4
    embedder.embed_one.return_value = [0.0, 0.0, 0.0, 0.0]
    embedder.embed.return_value = [[0.0, 0.0, 0.0, 0.0]]
    monkeypatch.setattr(rag_routes, "get_embedder", lambda: embedder)
    return embedder


def _login(client: TestClient) -> None:
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text


def test_query_via_cookie_session_returns_200(fake_qdrant) -> None:
    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/query",
            json={"query": "operator console test", "limit": 3},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "hits" in body
        assert body["query"] == "operator console test"


def test_ingest_via_cookie_session_returns_200(fake_qdrant) -> None:
    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/ingest",
            json={"text": "ABS test doc body — round 2 round 3"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["chunks"] >= 1
        assert "doc_id" in body


def test_query_no_cookie_no_bearer_still_401() -> None:
    """Regression guard for the existing T-011 contract: anonymous
    callers (no cookie, no Bearer) must still get 401 missing_bearer_token."""
    with TestClient(app) as c:
        r = c.post(
            "/v1/rag/query",
            json={"query": "no auth", "limit": 3},
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "missing_bearer_token"


def test_invalid_bearer_overrides_cookie_session(fake_qdrant) -> None:
    """Bearer header takes priority — if it's malformed we 401, even if
    a valid cookie session is also present."""
    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/query",
            json={"query": "bearer wins", "limit": 3},
            headers={"Authorization": "Bearer not-a-jwt-token"},
        )
        assert r.status_code == 401
        # Detail string starts with "invalid_token:" from OAuth verify.
        assert "invalid_token" in r.json().get("detail", "")
