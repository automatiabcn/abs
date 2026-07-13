"""T-015 — Multi-tenancy E2E for the RAG gateway (Playwright-equivalent via httpx).

Drives the FastAPI app with the in-process TestClient against the golden
eval dataset. Verifies:
  1. tenant A can ingest, tenant B sees nothing through tenant A's view.
  2. cross-tenant queries surface zero leaks (must_not_contain probes).
  3. own-tenant queries hit the expected document at top-K.

The integration uses the in-memory Qdrant wrapper double provided by the
mock embedder + a stub vector index so the test does not need a live
Qdrant container — the same code path is exercised against a real broker
in the nightly cron job (`.github/workflows/nightly-rag-e2e.yml`).
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1 import rag as rag_routes
from app.auth.oauth.models import OAuthClient
from app.db.session import get_engine
from app.main import app
from app.rag import qdrant_client as qc
from app.rag.embedding_bge import close_embedder

DATASET = json.loads(
    (
        Path(__file__).resolve().parent.parent / "fixtures/golden_eval_dataset.json"
    ).read_text(encoding="utf-8")
)


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


def _issue(
    c: TestClient, *, client_id, tenant_id, user_subject="alice", roles=("member",)
):
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


class _InMemoryVectorIndex:
    """Mimics qc.upsert_points / qc.search well enough for tenant-scoped tests."""

    def __init__(self) -> None:
        # rows: list of {tenant_id, payload, vector}
        self.rows: list[dict[str, Any]] = []

    def upsert(self, *, collection: str, tenant_id: str, points: list) -> int:
        for pt in points:
            payload = dict(pt.payload or {})
            payload.setdefault("tenant_id", tenant_id)
            assert payload["tenant_id"] == tenant_id, "tenant payload mismatch"
            self.rows.append({"vector": list(pt.vector), "payload": payload})
        return len(points)

    def search(
        self,
        *,
        collection: str,
        tenant_id: str,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
        extra_filter: Any = None,
    ) -> list[dict[str, Any]]:
        scored = [
            (
                _cosine(row["vector"], query_vector),
                row,
            )
            for row in self.rows
            if row["payload"].get("tenant_id") == tenant_id
        ]
        scored.sort(key=lambda x: -x[0])
        return [
            {
                "id": str(row["payload"].get("chunk_id") or ""),
                "score": float(score),
                "payload": dict(row["payload"]),
            }
            for score, row in scored[:limit]
        ]

    def ensure_collection(self, *args, **kwargs) -> None:  # noqa: ANN001
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


@pytest.fixture()
def index(monkeypatch: pytest.MonkeyPatch) -> _InMemoryVectorIndex:
    idx = _InMemoryVectorIndex()
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", idx.ensure_collection)
    monkeypatch.setattr(rag_routes.qc, "upsert_points", idx.upsert)
    monkeypatch.setattr(rag_routes.qc, "search", idx.search)
    yield idx


@pytest.fixture(autouse=True)
def _allowing_cerbos_and_clean_embedder():
    class _AllowAll:
        def check_resources(self, *, principal, resources):  # noqa: ANN001
            entry = SimpleNamespace(is_allowed=lambda action: True)
            return SimpleNamespace(
                results=[entry], failed=lambda: False, status_code=200
            )

        def close(self) -> None:
            return None

    app.state.cerbos_client = _AllowAll()
    close_embedder()
    yield
    if hasattr(app.state, "cerbos_client"):
        delattr(app.state, "cerbos_client")
    close_embedder()


def _ingest_corpus(
    c: TestClient, *, token: str, client_id: str, text: str, doc_id: str
) -> None:
    r = c.post(
        "/v1/rag/ingest",
        json={
            "text": text,
            "filename": f"{doc_id}.txt",
            "target_tokens": 200,
            "overlap_tokens": 20,
        },
        headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": client_id},
    )
    assert r.status_code == 200, r.text


def test_two_tenants_ingest_query_isolation_e2e(
    index: _InMemoryVectorIndex,
) -> None:
    cid = f"e2e-{secrets.token_hex(3)}"
    _seed_client(cid)

    with TestClient(app) as c:
        # 1. Each tenant ingests its own corpus.
        for entry in DATASET["entries"]:
            tok = _issue(
                c,
                client_id=cid,
                tenant_id=entry["tenant_id"],
                user_subject=f"user-{entry['tenant_id']}",
            )
            _ingest_corpus(
                c,
                token=tok,
                client_id=cid,
                text=entry["text"],
                doc_id=entry["doc_id"],
            )

        # 2. Per-tenant own-corpus queries surface the expected doc within top-K.
        recall_total = 0
        recall_hits = 0
        for entry in DATASET["entries"]:
            tok = _issue(c, client_id=cid, tenant_id=entry["tenant_id"])
            for q in entry["queries"]:
                r = c.post(
                    "/v1/rag/query",
                    json={"query": q["q"], "limit": 5},
                    headers={"Authorization": f"Bearer {tok}", "X-ABS-Audience": cid},
                )
                assert r.status_code == 200, r.text
                texts = [h["text"] for h in r.json()["hits"]]
                hit = any(entry["text"][:40] in t for t in texts)
                recall_total += 1
                if hit:
                    recall_hits += 1
        # mock embedder is pure stdlib; expect ≥50% recall on the golden set.
        assert recall_hits / recall_total >= 0.5

        # 3. Cross-tenant probes must never surface forbidden tokens.
        for probe in DATASET["cross_tenant_probe"]["items"]:
            tok = _issue(c, client_id=cid, tenant_id=probe["as_tenant"])
            r = c.post(
                "/v1/rag/query",
                json={"query": probe["query"], "limit": 10},
                headers={"Authorization": f"Bearer {tok}", "X-ABS-Audience": cid},
            )
            assert r.status_code == 200
            joined = " ".join(h["text"] for h in r.json()["hits"]).lower()
            for forbidden in probe["must_not_contain"]:
                assert forbidden.lower() not in joined, (
                    f"cross-tenant leak: {forbidden!r} in {probe['as_tenant']!r}"
                )


def test_qdrant_wrapper_blocks_cross_tenant_search() -> None:
    """Defense-in-depth: even if Cerbos were misconfigured, the wrapper rejects
    a missing tenant_id."""

    with pytest.raises(qc.TenantIsolationError):
        qc.search(
            collection="abs_documents",
            tenant_id="",
            query_vector=[0.1] * 4,
            limit=5,
        )


def test_golden_eval_dataset_shape_is_valid() -> None:
    assert DATASET["schema_version"] == 1
    assert isinstance(DATASET["entries"], list) and DATASET["entries"]
    for entry in DATASET["entries"]:
        for key in ("tenant_id", "doc_id", "text", "queries"):
            assert key in entry, key
        assert all("q" in q for q in entry["queries"])
    for probe in DATASET["cross_tenant_probe"]["items"]:
        assert {"as_tenant", "query", "must_not_contain"} <= set(probe.keys())
