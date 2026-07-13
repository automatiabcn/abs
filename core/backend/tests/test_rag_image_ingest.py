# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Gemini image → RAG (roadmap c).

Images have no native embedding in Gemini, so an image is vision-described and
the description is embedded into the SAME text index, tagged kind="image". The
image is then retrievable by the existing /query, and the panel can scope a
query to one modality via QueryRequest.kinds.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import rag as rag_routes
from app.main import app
from app.providers import gemini_extras as gx
from app.providers.schemas import ProviderError


# ---- describe_image (provider) -------------------------------------------


def test_describe_image_returns_vision_text(monkeypatch):
    async def _fake_post(url, body, *, key, timeout=90.0):
        # the image part is forwarded as inlineData
        parts = body["contents"][0]["parts"]
        assert any("inlineData" in p for p in parts)
        return {"candidates": [{"content": {"parts": [{"text": "a red invoice"}]}}]}

    monkeypatch.setattr(gx.settings, "gemini_api_key", "AIzaTESTKEY123456789")
    monkeypatch.setattr(gx, "_post", _fake_post)
    out = asyncio.run(gx.describe_image("Zm9v", "image/png"))
    assert out.text == "a red invoice"
    assert out.provider == "gemini"


def test_describe_image_without_key_raises(monkeypatch):
    monkeypatch.setattr(gx.settings, "gemini_api_key", "")
    with pytest.raises(ProviderError):
        asyncio.run(gx.describe_image("Zm9v", "image/png"))


# ---- ingest-image endpoint ------------------------------------------------


@pytest.fixture(autouse=True)
def _allow_cerbos():
    class _Allow:
        def check_resources(self, *, principal, resources):
            entry = SimpleNamespace(is_allowed=lambda action: True)
            return SimpleNamespace(
                results=[entry], failed=lambda: False, status_code=200
            )

        def close(self):
            return None

    app.state.cerbos_client = _Allow()
    yield
    if hasattr(app.state, "cerbos_client"):
        delattr(app.state, "cerbos_client")


def _login(c: TestClient) -> None:
    r = c.post("/auth/login", json={"email": "admin@local", "password": "CHANGEME"})
    assert r.status_code == 200, r.text


def _stub_embed_and_qdrant(monkeypatch) -> dict:
    captured: dict = {}
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)

    def _upsert(**k):
        captured["points"] = k["points"]
        return len(k["points"])

    monkeypatch.setattr(rag_routes.qc, "upsert_points", _upsert)
    embedder = MagicMock()
    embedder.dim = 4
    embedder.embed.side_effect = lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts]
    embedder.embed_one.return_value = [0.1, 0.2, 0.3, 0.4]
    monkeypatch.setattr(rag_routes, "get_embedder", lambda: embedder)
    return captured


def test_ingest_image_stores_description_tagged_as_image(monkeypatch):
    captured = _stub_embed_and_qdrant(monkeypatch)

    async def _fake_describe(b64, mime, **kw):
        assert mime == "image/png"
        return SimpleNamespace(
            text="A red invoice with the total 42 EUR and a blue logo."
        )

    monkeypatch.setattr(gx, "describe_image", _fake_describe)

    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/ingest-image",
            files={"file": ("invoice.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
        )
    assert r.status_code == 200, r.text
    assert r.json()["chunks"] >= 1
    # the stored point carries the description text + kind=image metadata
    pts = captured["points"]
    assert pts and pts[0].payload["kind"] == "image"
    assert pts[0].payload["source_filename"] == "invoice.png"
    assert "invoice" in pts[0].payload["text"].lower()


def test_ingest_image_without_gemini_is_503(monkeypatch):
    _stub_embed_and_qdrant(monkeypatch)

    async def _boom(b64, mime, **kw):
        raise ProviderError("no key", provider="gemini", transient=False)

    monkeypatch.setattr(gx, "describe_image", _boom)
    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/ingest-image",
            files={"file": ("x.png", b"\x89PNGfake", "image/png")},
        )
    assert r.status_code == 503
    assert "image_describe_unavailable" in r.text


def test_ingest_image_rejects_non_image(monkeypatch):
    _stub_embed_and_qdrant(monkeypatch)
    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/ingest-image",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
    assert r.status_code == 415


# ---- unified query kind filter -------------------------------------------


def test_query_kinds_image_adds_kind_filter(monkeypatch):
    captured: dict = {}

    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)

    def _search(**k):
        captured["filter"] = k.get("extra_filter")
        return []

    monkeypatch.setattr(rag_routes.qc, "search", _search)
    embedder = MagicMock()
    embedder.dim = 4
    embedder.embed_one.return_value = [0.1, 0.2, 0.3, 0.4]
    monkeypatch.setattr(rag_routes, "get_embedder", lambda: embedder)

    with TestClient(app) as c:
        _login(c)
        r = c.post("/v1/rag/query", json={"query": "logo", "kinds": ["image"]})
    assert r.status_code == 200, r.text
    flt = captured["filter"]
    assert flt is not None
    assert any(getattr(fc, "key", None) == "kind" for fc in (flt.must or []))


def test_query_by_image_describes_then_searches(monkeypatch):
    """Upload an image as the QUERY: it is vision-described, the description is
    embedded + searched, and the hits + description come back."""
    captured: dict = {}
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)

    def _search(**k):
        captured["filter"] = k.get("extra_filter")
        return [
            {
                "id": "c9",
                "score": 0.77,
                "payload": {
                    "doc_id": "d9",
                    "chunk_id": "c9",
                    "seq": 0,
                    "text": "matching policy doc",
                    "tenant_id": k["tenant_id"],
                },
            }
        ]

    monkeypatch.setattr(rag_routes.qc, "search", _search)
    embedder = MagicMock()
    embedder.dim = 4
    embedder.embed_one.return_value = [0.1, 0.2, 0.3, 0.4]
    monkeypatch.setattr(rag_routes, "get_embedder", lambda: embedder)

    async def _fake_describe(b64, mime, **kw):
        return SimpleNamespace(text="a screenshot of a pricing table")

    monkeypatch.setattr(gx, "describe_image", _fake_describe)

    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/query-by-image?kinds=image",
            files={"file": ("q.png", b"\x89PNGfake", "image/png")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["description"] == "a screenshot of a pricing table"
    assert len(body["hits"]) == 1 and body["hits"][0]["doc_id"] == "d9"
    # kinds=image scoped the search
    flt = captured["filter"]
    assert any(getattr(fc, "key", None) == "kind" for fc in (flt.must or []))


def test_query_by_image_without_gemini_is_503(monkeypatch):
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)

    async def _boom(b64, mime, **kw):
        raise ProviderError("no key", provider="gemini", transient=False)

    monkeypatch.setattr(gx, "describe_image", _boom)
    with TestClient(app) as c:
        _login(c)
        r = c.post(
            "/v1/rag/query-by-image",
            files={"file": ("q.png", b"\x89PNGfake", "image/png")},
        )
    assert r.status_code == 503


def test_query_kinds_text_excludes_images(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)

    def _search(**k):
        captured["filter"] = k.get("extra_filter")
        return []

    monkeypatch.setattr(rag_routes.qc, "search", _search)
    embedder = MagicMock()
    embedder.dim = 4
    embedder.embed_one.return_value = [0.1, 0.2, 0.3, 0.4]
    monkeypatch.setattr(rag_routes, "get_embedder", lambda: embedder)

    with TestClient(app) as c:
        _login(c)
        r = c.post("/v1/rag/query", json={"query": "policy", "kinds": ["text"]})
    assert r.status_code == 200, r.text
    flt = captured["filter"]
    assert flt is not None
    assert any(getattr(fc, "key", None) == "kind" for fc in (flt.must_not or []))
