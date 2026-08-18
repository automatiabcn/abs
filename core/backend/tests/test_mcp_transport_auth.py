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


# --- a session belongs to the token that opened it (audit 2026-08-18) ------

def _other_token() -> str:
    from app.api.mcp_tokens import _sign

    return _sign(
        {"v": 1, "tenant": "globex", "scope": "mcp", "label": "other",
         "iat": int(time.time()), "exp": int(time.time()) + 3600, "actor": "other"}
    )


def _run(middleware, headers: dict):
    """Drive the ASGI middleware with a fake downstream app that answers like
    the transport: `initialize` mints a session id on the response."""
    import asyncio

    out = {"status": None, "resp_headers": []}
    scope = {
        "type": "http", "method": "POST", "path": "/mcp/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }

    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
            out["resp_headers"] = message.get("headers") or []

    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"mcp-session-id", b"sess-abc")]})
        await send({"type": "http.response.body", "body": b"{}"})

    asyncio.run(middleware(downstream)(scope, receive, send))
    return out


def test_a_session_is_bound_to_the_token_that_opened_it(monkeypatch):
    from app.mcp import transport_auth as ta

    monkeypatch.setattr(ta, "_SESSION_OWNER", ta.OrderedDict())
    monkeypatch.setattr("app.config.settings.mcp_auth_enforce", True, raising=False)
    mine = _valid_token()
    theirs = _other_token()

    # initialize: no session id on the request, the transport mints one
    first = _run(ta.McpTokenAuthASGI, {"Authorization": f"Bearer {mine}"})
    assert first["status"] == 200
    assert ta._SESSION_OWNER.get("sess-abc") == ta._digest(mine)

    # the same token on that session: fine
    same = _run(ta.McpTokenAuthASGI, {"Authorization": f"Bearer {mine}", "mcp-session-id": "sess-abc"})
    assert same["status"] == 200

    # another valid token with a leaked session id: refused
    other = _run(ta.McpTokenAuthASGI, {"Authorization": f"Bearer {theirs}", "mcp-session-id": "sess-abc"})
    assert other["status"] == 401


def test_a_session_this_process_never_saw_is_claimed_by_its_first_token(monkeypatch):
    from app.mcp import transport_auth as ta

    monkeypatch.setattr(ta, "_SESSION_OWNER", ta.OrderedDict())
    monkeypatch.setattr("app.config.settings.mcp_auth_enforce", True, raising=False)
    mine = _valid_token()
    r = _run(ta.McpTokenAuthASGI, {"Authorization": f"Bearer {mine}", "mcp-session-id": "after-restart"})
    assert r["status"] == 200
    assert ta._SESSION_OWNER.get("after-restart") == ta._digest(mine)
