"""RAG quality fixes from founder feedback 2026-06-06.

Covers: ~400-char chunking, pre-chunk text cleaning + Turkish normalization,
LLM-synthesized answer on /query, document delete, and metadata (doc_ids)
filtering.
"""

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
from app.main import app
from app.rag import pipeline_v10 as pipe


# ── pipeline: text cleaning ─────────────────────────────────────────────────


def test_clean_text_preserves_turkish_and_strips_noise() -> None:
    dirty = "Şirket­ raporu� ﬁnans​ verileri.\x07 İstanbul ğ ü ç ö."
    clean = pipe._clean_text(dirty)
    assert "Şirket raporu finans verileri." in clean
    assert "İstanbul ğ ü ç ö." in clean
    assert "�" not in clean  # replacement char gone
    assert "​" not in clean and "­" not in clean  # zero-width/soft-hyphen
    assert "ﬁ" not in clean and "fi" in clean  # ligature expanded
    assert "\x07" not in clean  # control char gone


def test_clean_text_collapses_whitespace() -> None:
    assert pipe._clean_text("a    b\t\tc") == "a b c"
    assert pipe._clean_text("line1\n\n\n\n\nline2") == "line1\n\nline2"
    assert pipe._clean_text("trailing   \nnext") == "trailing\nnext"


def test_parse_text_applies_cleaning() -> None:
    doc = pipe.parse_text("Ｗ�rd​ içerik.", filename="x.txt")
    assert "�" not in doc.text and "​" not in doc.text
    assert "içerik" in doc.text  # Turkish preserved


def test_parse_text_still_normalizes_crlf_and_bom() -> None:
    # Regression: original T-011 contract must hold after cleaning was added.
    doc = pipe.parse_text(b"\xef\xbb\xbfhello\r\nworld", filename="t.txt")
    assert doc.text == "hello\nworld"


# ── pipeline: ~400-char chunking ────────────────────────────────────────────


def test_default_chunks_cap_around_400_chars() -> None:
    text = ". ".join(["cümle " * 10 for _ in range(60)])
    doc = pipe.parse_text(text, filename="big.txt")
    chunks = pipe.late_chunks(doc)  # defaults
    assert len(chunks) >= 2
    assert max(len(c.raw_text) for c in chunks) <= 400
    assert chunks[-1].char_end == len(doc.text)


def test_char_params_take_effect() -> None:
    text = "a. " * 500
    doc = pipe.parse_text(text, filename="c.txt")
    big = pipe.late_chunks(doc, target_chars=1000, overlap_chars=100)
    small = pipe.late_chunks(doc, target_chars=200, overlap_chars=40)
    assert len(small) > len(big)


def test_token_params_back_compat_override_chars() -> None:
    # Legacy callers passing target_tokens must keep identical behavior:
    # target_tokens=200 → 800-char window (200*4), regardless of char defaults.
    text = ". ".join(["sentence " * 20 for _ in range(40)])
    doc = pipe.parse_text(text, filename="big.txt")
    chunks = pipe.late_chunks(doc, target_tokens=200, overlap_tokens=20)
    assert max(len(c.raw_text) for c in chunks) <= 800
    assert [c.seq for c in chunks] == list(range(len(chunks)))


# ── HTTP route tests ────────────────────────────────────────────────────────


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


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


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


def _headers(c: TestClient, *, cid: str, tenant_id: str) -> dict[str, str]:
    verifier = "v" * 64
    auth = c.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://app.local/callback",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "scope": "rag:query",
            "user_subject": "u1",
            "tenant_id": tenant_id,
            "roles": "member",
        },
        follow_redirects=False,
    )
    code = auth.headers["location"].split("code=", 1)[1].split("&", 1)[0]
    tok = c.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": cid,
            "code": code,
            "redirect_uri": "https://app.local/callback",
            "code_verifier": verifier,
        },
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "X-ABS-Audience": cid}


def test_delete_document_route(monkeypatch: pytest.MonkeyPatch) -> None:
    cid = f"rag-{secrets.token_hex(3)}"
    _seed_client(cid)
    captured: dict = {}

    def fake_delete(*, collection, tenant_id, doc_id, project_id=None):
        captured["tenant_id"] = tenant_id
        captured["doc_id"] = doc_id
        captured["project_id"] = project_id
        return 7

    monkeypatch.setattr(rag_routes.qc, "delete_document", fake_delete)
    with TestClient(app) as c:
        h = _headers(c, cid=cid, tenant_id="tnt-del")
        r = c.delete("/v1/rag/documents/abc123", headers=h)
    assert r.status_code == 200, r.text
    # graph_purged is None when GraphRAG is disabled (the default test env); when
    # enabled, deleting a doc also purges its knowledge-graph chunks/entities so
    # the graph never retains orphans for a document removed from the corpus.
    assert r.json() == {"doc_id": "abc123", "deleted": 7, "graph_purged": None}
    # no X-Project-Id header ⇒ tenant-wide delete (project_id None), unchanged
    assert captured == {"tenant_id": "tnt-del", "doc_id": "abc123", "project_id": None}


def test_delete_document_purges_graph_when_graphrag_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock the orphan fix: with GraphRAG enabled, deleting a RAG document must
    also purge its knowledge-graph chunks/entities so Neo4j never retains
    orphans for a document removed from the corpus."""
    import app.graph_rag.store as gr_store
    from app.config import settings as _settings

    cid = f"rag-{secrets.token_hex(3)}"
    _seed_client(cid)
    monkeypatch.setattr(_settings, "graphrag_enabled", True)
    monkeypatch.setattr(
        rag_routes.qc,
        "delete_document",
        lambda *, collection, tenant_id, doc_id, project_id=None: 5,
    )
    purged: dict = {}

    async def fake_purge(client, *, tenant_id, doc_id):
        purged["tenant_id"] = tenant_id
        purged["doc_id"] = doc_id

    monkeypatch.setattr(gr_store, "purge_doc_graph", fake_purge)
    with TestClient(app) as c:
        h = _headers(c, cid=cid, tenant_id="tnt-g")
        r = c.delete("/v1/rag/documents/docXYZ", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["graph_purged"] is True
    assert purged == {"tenant_id": "tnt-g", "doc_id": "docXYZ"}


def test_list_documents_scopes_inventory_by_active_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock the project-scope consistency fix: the document inventory honours
    the active project (X-Project-Id) the same way the query path does, so a
    project workspace lists only its own documents (no header ⇒ tenant-wide)."""
    cid = f"rag-{secrets.token_hex(3)}"
    _seed_client(cid)
    captured: dict = {}

    def fake_list(*, collection, tenant_id, project_id=None, max_points=5000):
        captured["project_id"] = project_id
        return []

    monkeypatch.setattr(rag_routes.qc, "list_documents", fake_list)
    # bypass project-membership resolution to isolate the route→qc wiring
    monkeypatch.setattr(rag_routes, "_active_project", lambda request, auth: "proj-x")
    with TestClient(app) as c:
        h = _headers(c, cid=cid, tenant_id="tnt-p")
        r = c.get("/v1/rag/documents", headers=h)
    assert r.status_code == 200, r.text
    assert captured["project_id"] == "proj-x"


def test_query_synthesizes_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    cid = f"rag-{secrets.token_hex(3)}"
    _seed_client(cid)
    fake_hits = [
        {
            "id": "p1",
            "score": 0.9,
            "payload": {
                "chunk_id": "p1", "doc_id": "d1", "seq": 0,
                "text": "Kira her ayın 5'inde ödenir.",
            },
        }
    ]
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "search", lambda *a, **k: fake_hits)

    import app.providers.cascade as casc
    import app.cascade.orchestrator as orch

    monkeypatch.setattr(casc, "get_active_providers", lambda *a, **k: ["groq"])

    async def _fake_cascade(prompt, **kwargs):
        assert "Kira" in prompt  # the hit text is in the synthesis prompt
        return SimpleNamespace(text="Kira ayın 5'inde ödenir [1].")

    monkeypatch.setattr(orch, "call_with_cascade", _fake_cascade)

    with TestClient(app) as c:
        h = _headers(c, cid=cid, tenant_id="tnt-ans")
        r = c.post(
            "/v1/rag/query",
            json={"query": "Kira ne zaman ödenir?", "answer": True},
            headers=h,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "Kira ayın 5'inde ödenir [1]."
    assert len(body["hits"]) == 1


def test_query_without_answer_flag_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    cid = f"rag-{secrets.token_hex(3)}"
    _seed_client(cid)
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "search", lambda *a, **k: [])
    with TestClient(app) as c:
        h = _headers(c, cid=cid, tenant_id="tnt-noans")
        r = c.post("/v1/rag/query", json={"query": "x"}, headers=h)
    assert r.status_code == 200
    assert r.json()["answer"] is None


def test_query_doc_ids_filter_passed_to_search(monkeypatch: pytest.MonkeyPatch) -> None:
    cid = f"rag-{secrets.token_hex(3)}"
    _seed_client(cid)
    captured: dict = {}

    def fake_search(*, collection, tenant_id, query_vector, limit, score_threshold=None, extra_filter=None):
        captured["extra_filter"] = extra_filter
        return []

    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "search", fake_search)
    with TestClient(app) as c:
        h = _headers(c, cid=cid, tenant_id="tnt-filt")
        r = c.post(
            "/v1/rag/query",
            json={"query": "x", "doc_ids": ["d1", "d2"]},
            headers=h,
        )
    assert r.status_code == 200
    assert captured["extra_filter"] is not None  # a doc_id filter was built
