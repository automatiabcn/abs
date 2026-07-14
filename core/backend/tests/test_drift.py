"""Q11 Round 21 / L15 — OpenAPI vs implementation drift scan.

Three contracts under test:

  1. Every documented path in /openapi.json actually responds with a
     non-405. Catches a refactor that drops the route handler but
     leaves the @router decorator (or vice versa).

  2. Every operation has at least one `responses` entry — empty
     response stanzas suggest the route was added without a
     response_model, breaking client codegen.

  3. Authenticated routes whose OpenAPI declares 401 actually return
     401 when called without auth (not 500 / not 403). Sample of the
     critical Q10/Q11 surfaces.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def openapi(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    return r.json()


class TestQ11L15PathReachability:
    """For every GET path in /openapi.json with no required params,
    issue a request and confirm the server responds (any non-405)."""

    def test_all_get_paths_reachable(self, client, openapi):
        unreachable: list[str] = []
        for path, methods in openapi["paths"].items():
            spec = methods.get("get")
            if not spec:
                continue
            # skip param-bearing paths — we'd need synthetic ids
            if "{" in path:
                continue
            r = client.get(path)
            if r.status_code == 405:
                unreachable.append(f"{path} → 405")
        assert not unreachable, (
            f"OpenAPI documents these GETs but server 405s: {unreachable}"
        )


class TestQ11L15ResponseStanzaPresence:
    def test_every_operation_documents_at_least_one_response(self, openapi):
        empty: list[str] = []
        for path, methods in openapi["paths"].items():
            for method, spec in methods.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                if not spec.get("responses"):
                    empty.append(f"{method.upper()} {path}")
        assert not empty, f"endpoints without any documented response: {empty}"


class TestQ11L15AuthGate401Conformance:
    """Sample critical authed routes — they MUST 401 (not 500/403)
    without bearer/cookie. Catches the case where a route forgets
    its auth dependency."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/v1/mcp/tokens/verify"),
            ("post", "/v1/hooks/quota-check"),
            ("post", "/v1/hooks/audit-log"),
            ("post", "/v1/hooks/session-start"),
        ],
    )
    def test_unauthed_returns_401(self, client, method, path):
        if method == "get":
            r = client.get(path)
        else:
            r = client.post(path, json={})
        assert r.status_code == 401, (
            f"{method.upper()} {path} expected 401 unauthed, got "
            f"{r.status_code}: {r.text[:100]}"
        )


class TestQ11L15RfcShape:
    """FastAPI default error shape is {"detail": str|object}. Catches a
    drift to a non-standard error envelope that breaks panel error
    parsing."""

    def test_error_response_has_detail_field(self, client):
        r = client.get("/v1/mcp/tokens/verify")
        assert r.status_code == 401
        body = r.json()
        assert "detail" in body, f"401 response shape drifted: {body}"

    def test_unauthed_hooks_post_with_invalid_body_still_401(self, client):
        """Q11-L15-001 regression guard: an unauthed POST that ALSO has
        an invalid body must 401 (auth check first), never 422 (schema
        leak)."""
        r = client.post("/v1/hooks/quota-check", json={"garbage": True})
        assert r.status_code == 401
        assert r.json()["detail"] == "missing_bearer_token"

        r2 = client.post("/v1/hooks/audit-log", json={})
        assert r2.status_code == 401
        assert r2.json()["detail"] == "missing_bearer_token"
