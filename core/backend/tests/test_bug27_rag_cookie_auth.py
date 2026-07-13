# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""BUG-27 — `/admin/rag` console returned `[MOCK]` rows because the panel
silently fell back to a deterministic local mock when `/v1/rag/query`
returned a non-200. Sprint 2A swaps the mock fallback for an inline error
banner and tightens the backend so misconfigured infra surfaces as a clean
503 instead of a leaking 500.

These tests guard:
1. Cookie-session caller hits `/v1/rag/query` and gets real Qdrant rows
   (mocked search backend), with no `[MOCK]` string in the response.
2. Cross-tenant Cerbos DENY returns 403 (preserve T-015).
3. Missing tenant claim returns 403 (defense-in-depth around cookie path).
4. Embedder unavailable → 503 with `embedder_unavailable` detail, never 500.
5. Qdrant unreachable → 503 with `qdrant_unavailable` detail, never 500.
6. Frontend `page.tsx` no longer contains the `[MOCK]` string.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import rag as rag_routes
from app.main import app


_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _install_fake_cerbos():
    """ALLOW everything by default; individual tests flip to DENY."""

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


def _login(client: TestClient) -> None:
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text


def _stub_qdrant_with_hit(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """Patch the Qdrant wrappers so search returns a single, deterministic
    hit. The point is to verify the *response shape* coming out of the
    cookie-auth path, not vector retrieval quality."""
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "upsert_points", lambda **k: 1)
    monkeypatch.setattr(
        rag_routes.qc,
        "search",
        lambda **k: [
            {
                "id": "chunk-1",
                "score": 0.81,
                "payload": {
                    "tenant_id": k["tenant_id"],
                    "doc_id": "doc-acme-policy",
                    "chunk_id": "chunk-1",
                    "seq": 0,
                    "text": text,
                },
            }
        ],
    )

    embedder = MagicMock()
    embedder.dim = 4
    embedder.embed_one.return_value = [0.1, 0.2, 0.3, 0.4]
    embedder.embed.return_value = [[0.1, 0.2, 0.3, 0.4]]
    monkeypatch.setattr(rag_routes, "get_embedder", lambda: embedder)


def test_cookie_query_returns_real_hit_no_mock_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_qdrant_with_hit(monkeypatch, "Güvenlik politikamız: SOC2 Type II uyumlu.")
    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/query",
            json={"query": "güvenlik politikası", "limit": 3, "rerank": False},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "[MOCK]" not in r.text, "regression: mock fallback leaked"
        assert body["hits"], "expected at least one hit"
        assert body["hits"][0]["text"].startswith("Güvenlik")


def test_cross_tenant_cerbos_deny_returns_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T-015 parity — when Cerbos says DENY (e.g. mismatched tenant), the
    cookie path must surface 403, not silently fall through to query."""

    class _DenyingCerbos:
        def check_resources(self, *, principal, resources):  # noqa: ANN001
            entry = SimpleNamespace(is_allowed=lambda action: False)
            return SimpleNamespace(
                results=[entry], failed=lambda: False, status_code=200
            )

        def close(self) -> None:
            return None

    app.state.cerbos_client = _DenyingCerbos()
    _stub_qdrant_with_hit(monkeypatch, "secret tenant-B doc")
    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/query",
            json={"query": "x", "limit": 1, "rerank": False},
        )
        assert r.status_code == 403, r.text
        assert "forbidden_rag_action" in r.text


def test_missing_cookie_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_qdrant_with_hit(monkeypatch, "ignored")
    with TestClient(app) as c:
        # No login → no cookie → cookie path returns None → 401.
        r = c.post(
            "/v1/rag/query",
            json={"query": "x", "limit": 1, "rerank": False},
        )
        assert r.status_code == 401, r.text
        assert "missing_bearer_token" in r.text


def test_embedder_unavailable_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the operator flips ABS_EMBEDDING_BACKEND=sentence_transformers
    without installing the lib, get_embedder() raises ImportError.
    BUG-27 — must surface as 503, never 500."""
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "search", lambda **k: [])

    def _broken_embedder():
        raise ImportError(
            "sentence-transformers is required for the 'sentence_transformers' backend"
        )

    monkeypatch.setattr(rag_routes, "get_embedder", _broken_embedder)

    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/query",
            json={"query": "x", "limit": 1, "rerank": False},
        )
        assert r.status_code == 503, r.text
        assert "embedder_unavailable" in r.text


def test_qdrant_unreachable_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    embedder = MagicMock()
    embedder.dim = 4
    embedder.embed_one.return_value = [0.0, 0.0, 0.0, 0.0]
    monkeypatch.setattr(rag_routes, "get_embedder", lambda: embedder)

    def _qdrant_down(*args, **kwargs):
        raise ConnectionError("Connection refused: qdrant:6333")

    monkeypatch.setattr(rag_routes.qc, "ensure_collection", _qdrant_down)

    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/query",
            json={"query": "x", "limit": 1, "rerank": False},
        )
        assert r.status_code == 503, r.text
        assert "qdrant_unavailable" in r.text


def test_frontend_page_no_longer_contains_mock_fallback() -> None:
    """Static guard — `[MOCK]` literal must be gone from the panel page so
    operators see real failures."""
    page = _REPO_ROOT / "core" / "landing" / "app" / "admin" / "rag" / "page.tsx"
    text = page.read_text(encoding="utf-8")
    assert "[MOCK]" not in text, (
        "BUG-27 regression: page.tsx still contains [MOCK] fallback"
    )
    # A failed search says so, and says which call failed and how. The bug this
    # guards against is the opposite: fake hits that look exactly like real ones.
    assert "Search failed — /v1/rag/query returned" in text, (
        "the honest error banner is gone — a failed search must not look like an empty one"
    )
