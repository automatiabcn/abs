"""T-012 — Cerbos RAG resource auth tests."""

from __future__ import annotations

import base64
import hashlib
import secrets
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


def _issue_token(
    c: TestClient,
    *,
    client_id: str,
    user_subject: str,
    tenant_id: str,
    roles: list[str],
) -> str:
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


class _ScriptedCerbos:
    """Fake Cerbos that replies with a fixed allow/deny."""

    def __init__(self, *, allow: bool):
        self.allow = allow
        self.calls: list[tuple] = []

    def check_resources(self, *, principal, resources):  # noqa: ANN001
        self.calls.append((principal, resources))
        entry = SimpleNamespace(is_allowed=lambda action: self.allow)
        return SimpleNamespace(
            results=[entry], failed=lambda: False, status_code=200
        )

    def close(self) -> None:
        return None


@pytest.fixture()
def install_cerbos():
    def _install(allow: bool) -> _ScriptedCerbos:
        fake = _ScriptedCerbos(allow=allow)
        app.state.cerbos_client = fake
        return fake

    yield _install
    if hasattr(app.state, "cerbos_client"):
        delattr(app.state, "cerbos_client")


def test_query_denied_by_cerbos_returns_403(
    monkeypatch: pytest.MonkeyPatch, install_cerbos
) -> None:
    cid = f"crp-{secrets.token_hex(3)}"
    _seed_client(cid)
    fake = install_cerbos(allow=False)
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(rag_routes.qc, "search", MagicMock())

    with TestClient(app) as c:
        token = _issue_token(
            c,
            client_id=cid,
            user_subject="alice",
            tenant_id="tenant-1",
            roles=["member"],
        )
        r = c.post(
            "/v1/rag/query",
            json={"query": "hello", "limit": 5},
            headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
        )
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden_rag_action"
    rag_routes.qc.search.assert_not_called()
    assert len(fake.calls) == 1
    principal, resources = fake.calls[0]
    assert principal.attr.get("tenant_id") == "tenant-1"
    ra = list(resources.resources)[0]
    assert ra.resource.kind == "rag_collection"
    assert ra.resource.attr.get("tenant_id") == "tenant-1"
    assert "query" in ra.actions


def test_ingest_denied_by_cerbos_returns_403(
    monkeypatch: pytest.MonkeyPatch, install_cerbos
) -> None:
    cid = f"crp-{secrets.token_hex(3)}"
    _seed_client(cid)
    install_cerbos(allow=False)
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    upsert = MagicMock()
    monkeypatch.setattr(rag_routes.qc, "upsert_points", upsert)

    with TestClient(app) as c:
        token = _issue_token(
            c,
            client_id=cid,
            user_subject="bob",
            tenant_id="tenant-2",
            roles=["member"],
        )
        r = c.post(
            "/v1/rag/ingest",
            json={"text": "secret", "filename": "x.txt"},
            headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
        )
    assert r.status_code == 403
    upsert.assert_not_called()


def test_query_allowed_when_cerbos_permits(
    monkeypatch: pytest.MonkeyPatch, install_cerbos
) -> None:
    cid = f"crp-{secrets.token_hex(3)}"
    _seed_client(cid)
    install_cerbos(allow=True)
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)
    monkeypatch.setattr(
        rag_routes.qc,
        "search",
        lambda *a, **k: [
            {
                "id": "d-0",
                "score": 0.5,
                "payload": {
                    "chunk_id": "d-0",
                    "doc_id": "d",
                    "seq": 0,
                    "text": "ok",
                    "tenant_id": "tenant-1",
                },
            }
        ],
    )

    with TestClient(app) as c:
        token = _issue_token(
            c,
            client_id=cid,
            user_subject="carol",
            tenant_id="tenant-1",
            roles=["member"],
        )
        r = c.post(
            "/v1/rag/query",
            json={"query": "hi", "limit": 3},
            headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
        )
    assert r.status_code == 200, r.text
    assert r.json()["hits"][0]["text"] == "ok"


def test_missing_tenant_short_circuits_before_cerbos(
    monkeypatch: pytest.MonkeyPatch, install_cerbos
) -> None:
    cid = f"crp-{secrets.token_hex(3)}"
    _seed_client(cid)
    fake = install_cerbos(allow=True)
    monkeypatch.setattr(rag_routes.qc, "ensure_collection", lambda *a, **k: None)

    with TestClient(app) as c:
        token = _issue_token(
            c,
            client_id=cid,
            user_subject="dan",
            tenant_id="",
            roles=["member"],
        )
        r = c.post(
            "/v1/rag/query",
            json={"query": "hi", "limit": 3},
            headers={"Authorization": f"Bearer {token}", "X-ABS-Audience": cid},
        )
    assert r.status_code == 403
    assert r.json()["detail"] == "missing_tenant_claim"
    assert fake.calls == []
