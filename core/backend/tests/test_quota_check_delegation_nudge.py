# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Turnkey-delegation round — the documented PreToolUse hook
(/v1/hooks/quota-check) now also delivers the active delegation nudge.

Customers wire PreToolUse → /v1/hooks/quota-check (CLAUDE_CODE_INTEGRATION.md).
Previously that only did quota gating; the delegate_nudge lived behind the
separate unauthenticated /v1/hooks/dispatch and was never wired client-side, so
any connecting client (Claude Code, Codex) got passive MCP/CLAUDE.md guidance
but no active hook nudge. Folding the nudge into quota-check makes delegation
work out of the box for whoever connects, with no extra hook.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fresh_nudge_rate(monkeypatch, tmp_path):
    # delegate_nudge rate-limits per pattern for 15 min via a file in
    # settings.cache_dir; isolate it so each test gets a fresh window.
    from app.config import settings

    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    # Reset the in-memory risky-tool counter — under the full suite other tests
    # accumulate quota-check hits for the same bootstrap tenant, which would
    # push this tenant past RISKY_HOURLY_LIMIT and flip allow→deny.
    from app.api import claude_code_hooks as cch

    with cch._risky_lock:
        cch._risky_window.clear()
    yield
    with cch._risky_lock:
        cch._risky_window.clear()


@pytest.fixture()
def admin_client(client):
    r = client.post(
        "/auth/login", json={"email": "admin@local", "password": "CHANGEME"}
    )
    assert r.status_code == 200, r.text
    return client


def _mint_hooks_token(admin_client) -> str:
    r = admin_client.post(
        "/v1/mcp/tokens", json={"label": "nudge", "scope": "hooks", "ttl_days": 1}
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_quota_check_adds_delegation_nudge_for_inline_analysis(admin_client):
    token = _mint_hooks_token(admin_client)
    cmd = 'python3 -c "data=[1,2,3]; analyze(data); calculate(data); summarize(data)"'
    r = admin_client.post(
        "/v1/hooks/quota-check",
        json={"tool_name": "Bash", "tool_input": {"command": cmd}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    hso = r.json()["hookSpecificOutput"]
    assert hso["permissionDecision"] == "allow"
    ctx = hso.get("additionalContext", "")
    assert "ABS delegation" in ctx
    assert "mcp__abs__ask_" in ctx  # points the client at a real MCP tool


def test_quota_check_no_nudge_for_plain_command(admin_client):
    token = _mint_hooks_token(admin_client)
    r = admin_client.post(
        "/v1/hooks/quota-check",
        json={"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    hso = r.json()["hookSpecificOutput"]
    assert hso["permissionDecision"] == "allow"
    # No delegatable pattern → no nudge noise.
    assert "additionalContext" not in hso
