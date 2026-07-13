"""MCP middleware — with_hooks decorator: tool yanıtına nudge ekler."""

from __future__ import annotations

import pytest

from app.config import settings
from app.mcp.middleware import with_hooks


@pytest.fixture(autouse=True)
def _tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))
    monkeypatch.setattr(settings, "hooks_enabled", True)
    monkeypatch.setattr(settings, "hooks_mode", "middleware")


@pytest.mark.asyncio
async def test_with_hooks_appends_nudge_to_response():
    @with_hooks("ask_gptoss")
    async def fake_tool(prompt: str) -> str:
        return f"ANSWER: {prompt}"

    out = await fake_tool("test prompt")
    assert out.startswith("ANSWER: test prompt")
    # The tool's own answer comes first and intact; the nudge is appended below
    # a marker, so a caller can tell the two apart.
    assert "[HOOK]" in out
    assert "mcp__abs__race_code" in out


@pytest.mark.asyncio
async def test_with_hooks_unknown_tool_no_nudge():
    @with_hooks("unknown_tool_xyz")
    async def fake_tool(prompt: str) -> str:
        return "OK"

    out = await fake_tool("x")
    # unknown tool MCP nudge haritasında yok → sadece base response
    assert out == "OK"


@pytest.mark.asyncio
async def test_with_hooks_disabled_no_wrap(monkeypatch):
    monkeypatch.setattr(settings, "hooks_enabled", False)

    @with_hooks("ask_gptoss")
    async def fake_tool(prompt: str) -> str:
        return "RAW"

    out = await fake_tool("x")
    assert out == "RAW"
