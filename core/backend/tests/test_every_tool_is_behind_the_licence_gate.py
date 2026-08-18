"""The licence gate covers every tool on the surface, not only the ones whose
author remembered @with_hooks.

Audit 2026-08-18: 24 tools (ask_haiku/sonnet/opus, ask_groq_fast, ask_gemini,
qual_*, race*, auto_verify_*, ...) served a lapsed subscription.
"""

from __future__ import annotations

import asyncio

import pytest

import app.mcp.server as srv
from app.mcp import middleware as mw


def test_no_registered_tool_is_left_ungated():
    tools = srv.mcp_server._tool_manager._tools
    ungated = [
        name for name, t in tools.items()
        if not getattr(t.fn, "_abs_gated", False) and name not in mw.GATE_EXEMPT
    ]
    assert ungated == [], ungated


def test_the_late_gate_blocks_when_the_licence_is_lapsed(monkeypatch):
    monkeypatch.setattr(mw.settings, "mcp_require_license", True, raising=False)
    monkeypatch.setattr("app.mcp.gate._gate_status", lambda: {"allowed": False})
    monkeypatch.setattr("app.mcp.gate._BLOCK_MESSAGE", "[BLOCKED] licence", raising=False)

    async def real(prompt: str) -> str:
        return "answered"

    gated = mw._license_gate_only("ask_x", real)
    assert asyncio.run(gated("hi")) == "[BLOCKED] licence"


def test_the_late_gate_lets_a_licensed_call_through(monkeypatch):
    monkeypatch.setattr(mw.settings, "mcp_require_license", True, raising=False)
    monkeypatch.setattr("app.mcp.gate._gate_status", lambda: {"allowed": True})

    async def real(prompt: str) -> str:
        return "answered"

    assert asyncio.run(mw._license_gate_only("ask_x", real)("hi")) == "answered"


def test_the_gate_fails_closed_when_it_cannot_decide(monkeypatch):
    monkeypatch.setattr(mw.settings, "mcp_require_license", True, raising=False)
    monkeypatch.setattr("app.mcp.gate._gate_status", lambda: (_ for _ in ()).throw(RuntimeError("db")))

    async def real() -> str:
        return "answered"

    out = asyncio.run(mw._license_gate_only("ask_x", real)())
    assert out == mw._GATE_ERROR_MESSAGE


def test_the_exempt_list_is_only_readouts_and_repairs():
    for name in mw.GATE_EXEMPT:
        assert any(w in name for w in ("status", "check")), name
