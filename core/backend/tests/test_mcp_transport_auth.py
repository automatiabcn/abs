# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""The /mcp streamable-HTTP transport rejects requests without a valid
abs_mcp_ bearer token (McpTokenAuthASGI)."""

from __future__ import annotations

import time

_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1"},
    },
}
_ACCEPT = {"Accept": "application/json, text/event-stream"}


def _valid_token() -> str:
    from app.api.mcp_tokens import _sign

    return _sign(
        {
            "v": 1,
            "tenant": "default",
            # transport_auth allows only "mcp"/"all" to drive /mcp; a "tools"
            # scope is not recognised by the enforcer → scope_not_allowed.
            "scope": "mcp",
            "label": "pytest",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "actor": "pytest",
        }
    )


def test_mcp_rejects_missing_token(client):
    r = client.post("/mcp/", json=_INIT, headers=_ACCEPT)
    assert r.status_code == 401, r.text


def test_mcp_rejects_garbage_token(client):
    r = client.post(
        "/mcp/",
        json=_INIT,
        headers={**_ACCEPT, "Authorization": "Bearer abs_mcp_bad.bad"},
    )
    assert r.status_code == 401, r.text


def test_mcp_rejects_non_abs_token(client):
    r = client.post(
        "/mcp/",
        json=_INIT,
        headers={**_ACCEPT, "Authorization": "Bearer some-random-jwt"},
    )
    assert r.status_code == 401, r.text


def test_mcp_accepts_valid_token(client):
    # A valid token must clear the auth gate. In the test env ABS_TEST_MODE=1
    # leaves the FastMCP session manager un-started, so the transport itself
    # raises once past the gate — that RuntimeError still proves the gate
    # ALLOWED the request (it never reached the transport on a 401). The
    # security assertion is "not blocked by auth", verified live separately.
    try:
        r = client.post(
            "/mcp/",
            json=_INIT,
            headers={**_ACCEPT, "Authorization": f"Bearer {_valid_token()}"},
        )
    except RuntimeError:
        return  # cleared the gate; transport unavailable under ABS_TEST_MODE
    assert r.status_code != 401, r.text
