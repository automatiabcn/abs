# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The /mcp transport, spoken for real, in a process where it actually runs.

Every other test in this suite runs with ``ABS_TEST_MODE=1``, and that flag makes
``lifespan`` return early — before ``mcp_server.session_manager.run()``. It has to:
the streamable-HTTP manager accepts exactly one ``run()`` per process, and each
TestClient fixture opens the lifespan again. So the mount exists in those tests and
the protocol behind it does not, which is why the one test we had could only assert
that ``/mcp`` was not a 404.

It is not a 404. It is a 307 — Starlette redirects a mount hit without its trailing
slash — so that assertion would have held even with the transport completely dead.
The endpoint a customer points Claude Code at was, in effect, untested.

This file boots the real application in a **separate process** with ``ABS_TEST_MODE``
unset, so the session manager starts, and then behaves like a customer: mint a token,
``initialize``, ``tools/list``, call a tool. It is the only place the JSON-RPC layer,
the bearer gate and the tool registry are exercised through the wire they ship on.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

# Signs the tokens on both sides of the process boundary: the test mints with it,
# the child server verifies with it. Long enough for the boot-time secret guard.
_SECRET = "mcp-transport-live-test-signing-key-0123456789"
_BOOT_TIMEOUT = 90.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _rpc(
    base: str,
    body: dict[str, Any],
    token: str | None = None,
    session_id: str | None = None,
) -> tuple[int, str, dict[str, str]]:
    """POST one JSON-RPC message to /mcp and return (status, raw body, headers).

    The trailing slash is deliberate: without it the mount answers 307 and urllib
    will not re-POST across a redirect. Response header names come back lowercased.
    """
    headers = {
        "Content-Type": "application/json",
        # The streamable-HTTP transport answers on either channel and picks SSE.
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if session_id:
        headers["mcp-session-id"] = session_id

    request = urllib.request.Request(
        f"{base}/mcp/", data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode(), _lower(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), _lower(exc.headers)


def _lower(headers: Any) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in headers.items()}


def _result(raw: str) -> dict[str, Any]:
    """Pull the JSON-RPC envelope out of a text/event-stream response."""
    for line in raw.splitlines():
        if line.startswith("data: "):
            return dict(json.loads(line[6:]))
    return dict(json.loads(raw))


def _mint(scope: str) -> str:
    """Mint a token with the product's own signing code, not a copy of it.

    Signing here and verifying in the child process is half the point: it is the
    same check a customer's ``POST /v1/mcp/tokens`` token goes through.
    """
    from app.api import mcp_tokens
    from app.config import settings

    settings.mcp_token_secret = _SECRET  # restored by the _restore_settings fixture
    now = int(time.time())
    return str(
        mcp_tokens._sign(
            {
                "v": 1,
                "tenant": "default",
                "scope": scope,
                "label": "transport-test",
                "iat": now,
                "exp": now + 600,
                "actor": "test@local",
            }
        )
    )


@pytest.fixture(scope="module")
def live_server(tmp_path_factory) -> Any:
    """The real app, in its own process, with the MCP session manager running."""
    workdir = tmp_path_factory.mktemp("mcp_live")
    data_dir = workdir / "data"
    data_dir.mkdir()

    # Skip the first-run wizard: it 307s every request to /setup otherwise, and a
    # redirected /mcp would look like a working one to a careless assertion.
    (data_dir / "setup_state.json").write_text(
        json.dumps(
            {
                "completed": True,
                "current_step": 6,
                "completed_steps": [
                    "admin",
                    "license",
                    "domain",
                    "anthropic",
                    "providers",
                    "review",
                ],
            }
        )
    )

    port = _free_port()
    env = dict(os.environ)
    env.pop("ABS_TEST_MODE", None)  # the entire reason this file exists
    env.update(
        {
            "ABS_ENV": "dev",
            "ABS_DATABASE_URL": f"sqlite:///{workdir / 'live.db'}",
            "ABS_DATA_DIR": str(data_dir),
            "ABS_SESSION_SECRET": _SECRET,
            "ABS_ADMIN_JWT_SECRET": _SECRET,
            "ABS_UNSUBSCRIBE_JWT_SECRET": _SECRET,
            "ABS_DELETE_CONFIRM_JWT_SECRET": _SECRET,
            "ABS_VAULT_AUDIT_HMAC_SECRET": _SECRET,
            "ABS_AUDIT_IP_SALT": _SECRET,
            "ABS_MCP_TOKEN_SECRET": _SECRET,
        }
    )

    log_path = workdir / "server.log"
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=str(Path(__file__).resolve().parent.parent),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + _BOOT_TIMEOUT
    try:
        while True:
            if proc.poll() is not None:
                pytest.fail(
                    "the server exited during boot:\n" + log_path.read_text()[-4000:]
                )
            if time.time() > deadline:
                pytest.fail(
                    f"the server never answered /healthz in {_BOOT_TIMEOUT:.0f}s:\n"
                    + log_path.read_text()[-4000:]
                )
            try:
                with urllib.request.urlopen(f"{base}/healthz", timeout=2):
                    break
            except Exception:
                time.sleep(0.5)
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover — hung shutdown
            proc.kill()


@pytest.fixture(scope="module")
def mcp_session(live_server) -> Any:
    """A completed MCP handshake: (base url, token, session id)."""
    token = _mint("mcp")
    status, raw, headers = _rpc(
        live_server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "abs-transport-test", "version": "1.0"},
            },
        },
        token=token,
    )
    assert status == 200, raw
    session_id = headers.get("mcp-session-id")
    assert session_id, f"the transport issued no session id: {headers}"

    # The protocol requires this before any request is served on the session.
    _rpc(
        live_server,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        token=token,
        session_id=session_id,
    )
    return live_server, token, session_id


def test_a_request_without_a_token_is_refused(live_server):
    """The gate is on the transport itself, not on a route behind it."""
    status, raw, headers = _rpc(
        live_server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert status == 401, raw
    assert headers.get("www-authenticate") == "Bearer"
    assert "missing_token" in raw


def test_a_hooks_scoped_token_cannot_drive_the_tools(live_server):
    """Scope is enforced where it matters — over the wire.

    A hooks token is issued for the hook endpoints. If it also opened /mcp it would
    hand its bearer all 120 tools, spending the operator's provider keys.
    """
    status, raw, _ = _rpc(
        live_server,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        token=_mint("hooks"),
    )
    assert status == 401, raw
    assert "scope_not_allowed" in raw


def test_the_handshake_completes_and_the_tools_are_listed(mcp_session):
    """What a customer's Claude Code does on connect, done for real."""
    base, token, session_id = mcp_session
    status, raw, _ = _rpc(
        base,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        token=token,
        session_id=session_id,
    )
    assert status == 200, raw

    payload = _result(raw)
    assert "error" not in payload, payload
    names = {tool["name"] for tool in payload["result"]["tools"]}

    # The registry is asserted in full elsewhere; here the question is only whether
    # it survives the trip through the transport at all.
    assert len(names) >= 100, f"only {len(names)} tools came through the wire"
    for expected in ("rag_query", "system_status", "code_review"):
        assert expected in names

    schema = next(t for t in payload["result"]["tools"] if t["name"] == "rag_query")
    assert schema["inputSchema"]["type"] == "object"


def test_a_tool_can_actually_be_called_over_the_transport(mcp_session):
    """Listing a tool is not the same as reaching one.

    `system_status` needs no provider key and no network, so a non-error result here
    means the JSON-RPC dispatch really landed in the registered function.
    """
    base, token, session_id = mcp_session
    status, raw, _ = _rpc(
        base,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "system_status", "arguments": {}},
        },
        token=token,
        session_id=session_id,
    )
    assert status == 200, raw

    payload = _result(raw)
    assert "error" not in payload, payload
    result = payload["result"]
    assert result.get("isError") is not True, result
    assert result["content"], "the tool returned an empty body"
