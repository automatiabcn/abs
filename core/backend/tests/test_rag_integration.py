"""integration roundtrip tests.

Three contracts that previously had only happy-path unit coverage:

  1. Cascade run + chat completions: prompt arrives, mock provider
     answers, SSE chunks land, assistant message persists, sidebar
     session list reflects the new message_count.

  2. Tool browser inventory: GET /v1/panel/tools returns the contract
     (total + category_counts + tools[]) the panel/tools page expects.

  3. Cascade providers status: GET /v1/cascade/providers structure
     used by /admin/providers cards (active + missing + total +
     anthropic_mock_mode).
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "ok")
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_mock_mode", "ok", raising=False)
    yield


@pytest.fixture()
def admin_client(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


# ───── 1. Cascade + chat roundtrip ──────────────────────────────────────


class TestCascadeChatRoundtrip:
    def test_completions_persists_user_and_assistant_messages(self, admin_client):
        # Fire a streaming completion, parse SSE, then verify the session
        # holds both rows.
        resp = admin_client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "integration ping"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        events = []
        for line in resp.content.decode("utf-8").splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                continue

        sess = next(e for e in events if e.get("type") == "session")
        sid = sess["session_id"]

        # text + meta event present
        assert any(e.get("type") == "text" for e in events)
        assert any(e.get("type") == "meta" for e in events)

        # GET messages list reflects user + assistant
        msgs = admin_client.get(f"/v1/chat/sessions/{sid}/messages").json()
        roles = [m["role"] for m in msgs]
        assert "user" in roles and "assistant" in roles

        # Session list includes our session with message_count >= 2
        sessions = admin_client.get("/v1/chat/sessions").json()
        ours = [s for s in sessions if s["id"] == sid]
        assert len(ours) == 1
        assert ours[0]["message_count"] >= 2

        # Cleanup so the suite stays idempotent under repeat runs.
        admin_client.delete(f"/v1/chat/sessions/{sid}")

    def test_cascade_run_direct_returns_mock_provider(self, admin_client):
        r = admin_client.post(
            "/v1/cascade/run",
            json={"prompt": "cascade ping", "max_tokens": 32},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["mock"] is True
        assert body["provider"] == "anthropic-mock"
        assert isinstance(body["fallback_chain"], list)
        assert "anthropic-mock" in body["fallback_chain"]


# ───── 2. Panel tool inventory contract ─────────────────────────────────


class TestPanelToolsContract:
    def test_panel_tools_returns_inventory_shape(self, admin_client):
        r = admin_client.get("/v1/panel/tools")
        assert r.status_code == 200
        body = r.json()
        assert "total" in body and isinstance(body["total"], int)
        assert "category_counts" in body
        assert isinstance(body["category_counts"], dict)
        assert "tools" in body and isinstance(body["tools"], list)

    def test_panel_tools_each_row_has_contract_fields(self, admin_client):
        body = admin_client.get("/v1/panel/tools").json()
        for tool in body["tools"][:10]:
            assert isinstance(tool["name"], str) and tool["name"]
            assert "category" in tool
            assert isinstance(tool.get("description", ""), str)
            schema = tool.get("input_schema") or {}
            assert "required" in schema
            assert "properties" in schema
            assert isinstance(schema["properties"], list)


# ───── 3. Cascade providers status contract ─────────────────────────────


class TestCascadeProvidersStatus:
    def test_providers_endpoint_shape(self, admin_client):
        r = admin_client.get("/v1/cascade/providers")
        assert r.status_code == 200
        body = r.json()
        for key in (
            "active",
            "missing",
            "configured_count",
            "total",
            "anthropic_mock_mode",
        ):
            assert key in body, f"missing key: {key}"
        assert isinstance(body["active"], list)
        assert isinstance(body["missing"], list)
        assert body["configured_count"] + len(body["missing"]) >= body["total"] - 1

    def test_providers_mock_mode_reflected(self, admin_client):
        body = admin_client.get("/v1/cascade/providers").json()
        # autouse fixture sets it to 'ok'
        assert body["anthropic_mock_mode"] == "ok"


# ───── 4. Chat session lifecycle (create → rename → delete) ─────────────


class TestChatSessionLifecycle:
    def test_session_create_rename_delete_cycle(self, admin_client):
        sid = admin_client.post("/v1/chat/sessions", json={"title": "probe"}).json()[
            "id"
        ]
        rename = admin_client.patch(
            f"/v1/chat/sessions/{sid}", json={"title": "renamed"}
        )
        assert rename.status_code == 200
        assert rename.json()["title"] == "renamed"

        d = admin_client.delete(f"/v1/chat/sessions/{sid}")
        assert d.status_code == 204
        again = admin_client.get(f"/v1/chat/sessions/{sid}/messages")
        assert again.status_code == 404


# ───── 5. an earlier release — RAG ingest+query roundtrip + cross-tenant ─────


class _StubQdrant:
    """In-memory Qdrant stand-in — keeps point payloads keyed by
    (collection, tenant_id) so a test can ingest from one tenant and
    confirm a different tenant gets zero hits without touching the
    real Qdrant binary.

    Mirrors only the surface that app.api.v1.rag uses:
    `ensure_collection`, `upsert_points`, `search`.
    """

    def __init__(self) -> None:
        self.points: dict[tuple[str, str], list[dict]] = {}

    def ensure_collection(self, *args, **kwargs) -> None:
        return None

    def upsert_points(self, *, collection, tenant_id, points) -> int:
        bucket = self.points.setdefault((collection, tenant_id), [])
        for p in points:
            bucket.append(
                {
                    "id": p.id,
                    "score": 0.93,
                    "payload": dict(p.payload),
                }
            )
        return len(points)

    def search(self, *, collection, tenant_id, query_vector, **kwargs):
        rows = self.points.get((collection, tenant_id), [])
        limit = kwargs.get("limit", 5)
        return rows[:limit]


class TestRagRoundtripAndIsolation:
    """RAG layer integration enrichment.

    The existing unit tests cover the ingest happy path and the query mock
    independently. These contracts wire them together: the same
    document round-trips through ingest → query, and a second tenant
    on the same collection sees zero of the first tenant's data.
    """

    @pytest.fixture(autouse=True)
    def _allow_cerbos(self):
        from types import SimpleNamespace
        from app.main import app

        class _AllowingCerbos:
            def check_resources(self, *, principal, resources):
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

    @staticmethod
    def _challenge(verifier: str) -> str:
        import base64
        import hashlib

        return (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )

    @classmethod
    def _seed_oauth_client(cls, client_id: str) -> None:
        from datetime import datetime, timezone
        from sqlmodel import Session
        from app.auth.oauth.models import OAuthClient
        from app.db.session import get_engine

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

    @classmethod
    def _issue_token(cls, c, *, client_id, user_subject, tenant_id, roles) -> str:
        verifier = "v" * 64
        auth = c.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "https://app.local/callback",
                "code_challenge": cls._challenge(verifier),
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

    def test_rag_ingest_then_query_returns_same_doc(self, client, monkeypatch):
        import secrets
        from app.api.v1 import rag as rag_routes

        stub = _StubQdrant()
        monkeypatch.setattr(rag_routes.qc, "ensure_collection", stub.ensure_collection)
        monkeypatch.setattr(rag_routes.qc, "upsert_points", stub.upsert_points)
        monkeypatch.setattr(rag_routes.qc, "search", stub.search)

        cid = f"rag-{secrets.token_hex(3)}"
        self._seed_oauth_client(cid)
        token = self._issue_token(
            client,
            client_id=cid,
            user_subject="alice",
            tenant_id="tenant-q10",
            roles=["member"],
        )
        headers = {"Authorization": f"Bearer {token}", "X-ABS-Audience": cid}

        # Ingest
        ingest = client.post(
            "/v1/rag/ingest",
            json={"text": "round 18 marker " * 60, "filename": "q10.txt"},
            headers=headers,
        )
        assert ingest.status_code == 200, ingest.text
        ingest_body = ingest.json()
        assert ingest_body["chunks"] >= 1
        original_doc_id = ingest_body["doc_id"]

        # Query — same tenant, should retrieve the chunk we just ingested.
        query = client.post(
            "/v1/rag/query",
            json={"query": "round 18 marker", "limit": 3},
            headers=headers,
        )
        assert query.status_code == 200, query.text
        hits = query.json()["hits"]
        assert len(hits) >= 1
        # The first hit must descend from the doc we just ingested.
        assert hits[0]["doc_id"] == original_doc_id
        assert "round 18 marker" in hits[0]["text"]

    def test_rag_cross_tenant_query_returns_zero_hits(self, client, monkeypatch):
        import secrets
        from app.api.v1 import rag as rag_routes

        stub = _StubQdrant()
        monkeypatch.setattr(rag_routes.qc, "ensure_collection", stub.ensure_collection)
        monkeypatch.setattr(rag_routes.qc, "upsert_points", stub.upsert_points)
        monkeypatch.setattr(rag_routes.qc, "search", stub.search)

        cid_a = f"rag-a-{secrets.token_hex(3)}"
        cid_b = f"rag-b-{secrets.token_hex(3)}"
        self._seed_oauth_client(cid_a)
        self._seed_oauth_client(cid_b)

        token_a = self._issue_token(
            client,
            client_id=cid_a,
            user_subject="alice",
            tenant_id="tenant-A",
            roles=["member"],
        )
        token_b = self._issue_token(
            client,
            client_id=cid_b,
            user_subject="bob",
            tenant_id="tenant-B",
            roles=["member"],
        )

        # Tenant A ingests confidential text.
        ingest = client.post(
            "/v1/rag/ingest",
            json={
                "text": "TENANT-A-ONLY confidential payload " * 80,
                "filename": "secret.txt",
            },
            headers={
                "Authorization": f"Bearer {token_a}",
                "X-ABS-Audience": cid_a,
            },
        )
        assert ingest.status_code == 200, ingest.text

        # Tenant B queries — must see zero hits despite identical wording.
        query = client.post(
            "/v1/rag/query",
            json={"query": "confidential payload", "limit": 5},
            headers={
                "Authorization": f"Bearer {token_b}",
                "X-ABS-Audience": cid_b,
            },
        )
        assert query.status_code == 200, query.text
        body = query.json()
        assert body["hits"] == [], (
            f"cross-tenant leak: {body['hits']!r} returned to tenant-B"
        )


# ───── 6. an earlier release — marketplace install→sandbox→uninstall lifecycle ─


class TestMarketplaceLifecycleRoundtrip:
    """full marketplace lifecycle in one test.

    Existing test_marketplace_hardening covers each step in isolation
    (install, idempotent, uninstall, cross-tenant). This test ties them
    together so a regression in any single step that breaks the chain is
    caught even if the per-step assertion still passes.
    """

    @pytest.fixture(autouse=True)
    def _cosign_skip(self, monkeypatch):
        # Skip cosign so install isn't gated on a real cosign binary.
        # Don't monkeypatch data_dir — session conftest already sets it
        # to a tmp dir, and overriding it here would invalidate the
        # bootstrap admin_credentials.json the admin_client login needs.
        from app.config import settings

        monkeypatch.setattr(settings, "cosign_skip", True)
        yield

    def test_install_then_uninstall_full_lifecycle(self, admin_client):
        # 1) install
        install = admin_client.post(
            "/v1/marketplace/install",
            json={"plugin_id": "slack-receiver", "tenant": "default"},
        )
        assert install.status_code == 201, install.text
        assert install.json()["status"] == "installed"

        # 2) /installed reflects the row (response key is "installed")
        listing = admin_client.get("/v1/marketplace/installed?tenant=default")
        assert listing.status_code == 200
        ids = [row["plugin_id"] for row in listing.json()["installed"]]
        assert "slack-receiver" in ids

        # 3) uninstall
        rm = admin_client.delete(
            "/v1/marketplace/uninstall/slack-receiver?tenant=default"
        )
        assert rm.status_code == 200, rm.text
        assert rm.json()["status"] == "uninstalled"

        # 4) /installed no longer contains the plugin
        post = admin_client.get("/v1/marketplace/installed?tenant=default")
        assert post.status_code == 200
        ids_after = [row["plugin_id"] for row in post.json()["installed"]]
        assert "slack-receiver" not in ids_after

        # 5) re-uninstall is now a 404
        again = admin_client.delete(
            "/v1/marketplace/uninstall/slack-receiver?tenant=default"
        )
        assert again.status_code == 404
