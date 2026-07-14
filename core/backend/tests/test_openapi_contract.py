"""OpenAPI contract regression coverage.

The FastAPI auto-generated /openapi.json is the source of truth for
client codegen and the panel's typed fetch wrappers. an earlier release
added /v1/mcp/tokens/revoke and /revoked but didn't add an OpenAPI
contract test, so a future refactor that drops the route from the
APIRouter would silently break clients.

This module pins the contract for:
  * endpoints  — /v1/mcp/tokens/revoke + /revoked
  * endpoint    — /v1/hooks/quota-check (needs to expose
                              the 200 hookSpecificOutput shape)
  * fix         — /v1/chat/completions input bounds
                              (min_length=1, max_length=8000)
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def openapi(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200, r.text
    return r.json()


class TestMcpTokenRoutes:
    def test_revoke_endpoint_documented(self, openapi):
        paths = openapi["paths"]
        assert "/v1/mcp/tokens/revoke" in paths, (
            "endpoint missing from OpenAPI — silent client breakage risk"
        )
        post = paths["/v1/mcp/tokens/revoke"].get("post")
        assert post is not None
        # 204 success per the @router.post(..., status_code=204) decorator
        assert "204" in post["responses"], (
            f"revoke must document 204, got {list(post['responses'])}"
        )

    def test_revoked_listing_endpoint_documented(self, openapi):
        paths = openapi["paths"]
        assert "/v1/mcp/tokens/revoked" in paths
        get = paths["/v1/mcp/tokens/revoked"].get("get")
        assert get is not None
        assert "200" in get["responses"]

    def test_revoke_request_schema_contract(self, openapi):
        schemas = openapi["components"]["schemas"]
        assert "RevokeTokenRequest" in schemas
        body = schemas["RevokeTokenRequest"]
        props = body["properties"]
        # Revoke accepts a raw token (legacy/paste) OR a digest (panel list).
        assert "token" in props
        assert "token_digest" in props
        assert "reason" in props

        # token still enforces min_length=16 — now optional, so the constraint
        # lives directly or inside the anyOf (string | null) union.
        def _min_len(p):
            if p.get("minLength") == 16:
                return True
            return any(v.get("minLength") == 16 for v in p.get("anyOf", []))

        assert _min_len(props["token"])

    def test_revoked_token_info_schema(self, openapi):
        schemas = openapi["components"]["schemas"]
        assert "RevokedTokenInfo" in schemas
        info = schemas["RevokedTokenInfo"]
        required = set(info["required"])
        # token_digest must be required so clients can rely on it
        assert "token_digest" in required
        assert "tenant_slug" in required
        assert "label" in required
        assert "revoked_by" in required
        assert "revoked_at" in required


class TestChatCompletionsContract:
    def test_chat_message_in_content_bounds_documented(self, openapi):
        """001/002 fix: pydantic Field(min_length=1, max_length=8000)
        must surface in OpenAPI so client codegen rejects oversized
        payloads at compile time."""
        schemas = openapi["components"]["schemas"]
        assert "ChatMessageIn" in schemas
        cm = schemas["ChatMessageIn"]
        content = cm["properties"]["content"]
        assert content.get("minLength") == 1, (
            "contract regression: content min_length lost"
        )
        assert content.get("maxLength") == 8000, (
            "contract regression: content max_length must "
            "mirror CascadeRequest.prompt's 8000-char ceiling"
        )


class TestHooksRoutes:
    def test_quota_check_endpoint_documented(self, openapi):
        paths = openapi["paths"]
        assert "/v1/hooks/quota-check" in paths
        post = paths["/v1/hooks/quota-check"].get("post")
        assert post is not None
        assert "200" in post["responses"]

    def test_audit_log_endpoint_documented(self, openapi):
        paths = openapi["paths"]
        assert "/v1/hooks/audit-log" in paths

    def test_session_start_endpoint_documented(self, openapi):
        paths = openapi["paths"]
        assert "/v1/hooks/session-start" in paths


class TestRagRoutes:
    """RAG endpoints power the customer demo + cross-tenant gate; their
    contract drift would silently break panel/admin/rag tooling."""

    def test_rag_ingest_documented(self, openapi):
        assert "/v1/rag/ingest" in openapi["paths"]

    def test_rag_query_documented(self, openapi):
        assert "/v1/rag/query" in openapi["paths"]
