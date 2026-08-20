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
import tempfile
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


# --- The editor's own tools, over the same wire the editor client uses --------
# These exercise the Faz B engine (codegraph, composer, notes) end-to-end through
# the JSON-RPC transport an ABS editor connects to — the server half of M1.


def _call(session, name, args, rid) -> str:
    """tools/call over the wire; returns the tool's text content (or fails loudly)."""
    base, token, session_id = session
    status, raw, _ = _rpc(
        base,
        {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
        token=token,
        session_id=session_id,
    )
    assert status == 200, raw
    payload = _result(raw)
    assert "error" not in payload, payload
    result = payload["result"]
    assert result.get("isError") is not True, result
    return str(result["content"][0]["text"])


def test_editor_code_graph_over_the_wire(mcp_session):
    """code_graph_build + code_blast_radius — the editor's blast-radius, over /mcp."""
    ws = tempfile.mkdtemp(prefix="abs_cg_")
    with open(os.path.join(ws, "util.py"), "w") as fh:
        fh.write("def helper():\n    return 1\n")
    with open(os.path.join(ws, "app.py"), "w") as fh:
        fh.write("def handler():\n    return helper()\n")

    build = json.loads(_call(mcp_session, "code_graph_build", {"root": ws}, 20))
    assert build["symbols"] >= 2 and build["edges"] >= 1

    blast = json.loads(_call(mcp_session, "code_blast_radius", {"target": "helper"}, 21))
    assert blast["found"] is True
    affected = {s["symbol"] for layer in blast["layers"] for s in layer["symbols"]}
    assert "handler" in affected  # helper's caller, resolved deterministically over the wire


def test_editor_composer_propose_over_the_wire(mcp_session):
    """composer_propose returns a well-formed ComposerRun over the wire.

    Whether the model produced any edits depends on what the live env has
    configured; the contract the editor relies on is the *shape*, not the count.
    """
    ws = tempfile.mkdtemp(prefix="abs_cmp_")
    run = json.loads(
        _call(mcp_session, "composer_propose", {"task": "noop", "workspace_root": ws}, 22)
    )
    assert run["run_id"].startswith("cmp-")
    assert isinstance(run["edits"], list)
    assert run["risk"] in ("low", "medium", "high")
    assert "requires_approval" in run
    assert isinstance(run["providers_tried"], list)


def test_editor_notes_over_the_wire(mcp_session):
    """note_save + note_search — the Notion-like companion, over /mcp."""
    saved = json.loads(
        _call(mcp_session, "note_save", {"title": "Cascade", "body": "provider failover notes"}, 23)
    )
    nid = saved["id"]
    hits = json.loads(_call(mcp_session, "note_search", {"query": "failover"}, 24))
    assert any(h["id"] == nid for h in hits)


def test_editor_opens_a_project_and_the_chat_knows_about_it(mcp_session):
    """The first thing a real tester reported, walked over the wire.

    They connected a provider, opened a project, asked the chat about it, and
    got an answer that had nothing to do with their code. Of the thirty-three
    tools the editor calls, only Composer sent the workspace, so opening a
    project made one feature project-aware and left the rest guessing.

    This is that sequence exactly as the editor performs it: announce the
    workspace, then ask. No model call is made — cascade_ask needs a provider
    and this suite has none — so what is asserted is the part that was broken:
    the server accepts the project, reports whether it has been read, and the
    retrieval that feeds the chat finds the file the question is about.
    """
    ws = tempfile.mkdtemp(prefix="abs_ws_")
    src = os.path.join(ws, "src")
    os.makedirs(src)
    with open(os.path.join(src, "invoices.py"), "w") as fh:
        fh.write(
            "VAT_CATALONIA = 0.21\n\n\n"
            "def compute_invoice_total(items):\n"
            "    net = sum(i.price * i.qty for i in items)\n"
            "    return round(net * (1 + VAT_CATALONIA), 2)\n"
        )
    with open(os.path.join(ws, "README.md"), "w") as fh:
        fh.write("# Ledger\nInvoicing for small studios. VAT lives in src/invoices.py.\n")

    announced = json.loads(_call(mcp_session, "workspace_set", {"root": ws}, 40))
    assert announced["ok"] is True
    assert announced["workspace"] == os.path.realpath(ws)
    # Nothing has indexed it, and the server has to say so rather than let the
    # editor assume silence means "no results".
    assert announced["indexed"] is False

    # The retrieval the chat uses, exercised through the tool the panel calls.
    graph = json.loads(_call(mcp_session, "code_graph_build", {"root": ws}, 41))
    assert graph["symbols"] >= 1

    reread = json.loads(_call(mcp_session, "workspace_set", {"root": ws}, 42))
    assert reread["indexed"] is True, "indexing the project did not register"

    hits = json.loads(
        _call(mcp_session, "symbol_search", {"q": "compute_invoice_total"}, 43)
    )
    assert hits["results"], "the project's own symbol is not findable after indexing"
    assert hits["scope"] == os.path.realpath(ws), (
        "the search was not scoped to the open project"
    )


def test_a_root_the_server_cannot_see_is_refused_over_the_wire(mcp_session):
    """The editor runs on a laptop; the server may be in a container.

    Accepting a path that does not resolve would leave every tool that trusts
    it answering about nothing — silence that reads like an empty repository.
    """
    out = json.loads(
        _call(mcp_session, "workspace_set", {"root": "/definitely/not/here"}, 44)
    )
    assert out["ok"] is False
    assert out["error"] == "not_a_directory"
    assert "mounted" in out["detail"]
