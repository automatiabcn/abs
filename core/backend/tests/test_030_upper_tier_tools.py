"""030 Modul E — Upper-tier + auto-upgrade alias tool tests."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.config import settings


def _openai_stub(content: str = "ok") -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


@respx.mock
@pytest.mark.asyncio
async def test_ask_cerebras_qwen_calls_cerebras(monkeypatch):
    from app.mcp.tools.upper_tier_tools import ask_cerebras_qwen

    monkeypatch.setattr(settings, "cerebras_api_key", "sk-cerebras")
    route = respx.post("https://api.cerebras.ai/v1/chat/completions").mock(
        return_value=_openai_stub("qwen ok")
    )
    out = await ask_cerebras_qwen("hi")
    assert "qwen ok" in out
    assert route.called


@pytest.mark.asyncio
async def test_ask_cerebras_qwen_graceful_when_key_missing(monkeypatch):
    """Without an API key the tool returns a graceful [ERROR] string,
    never crashes."""
    from app.mcp.tools.upper_tier_tools import ask_cerebras_qwen

    monkeypatch.setattr(settings, "cerebras_api_key", "")
    out = await ask_cerebras_qwen("cerebras-missing-key-uniqueness-probe")
    assert isinstance(out, str)
    assert "[ERROR]" in out


@respx.mock
@pytest.mark.asyncio
async def test_ask_gemini_latest_uses_flash_latest_model(monkeypatch):
    from app.mcp.tools.upper_tier_tools import ask_gemini_latest

    monkeypatch.setattr(settings, "gemini_api_key", "g-test")
    route = respx.post(
        url__regex=r"https://generativelanguage\.googleapis\.com/.*gemini-flash-latest.*"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "flash latest reply"}]}}]
            },
        )
    )
    out = await ask_gemini_latest("hi")
    assert "flash latest reply" in out
    assert route.called


@respx.mock
@pytest.mark.asyncio
async def test_ask_gemini_pro_latest_uses_pro_latest_model(monkeypatch):
    from app.mcp.tools.upper_tier_tools import ask_gemini_pro_latest

    monkeypatch.setattr(settings, "gemini_api_key", "g-test")
    route = respx.post(
        url__regex=r"https://generativelanguage\.googleapis\.com/.*gemini-pro-latest.*"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "pro latest reply"}]}}]
            },
        )
    )
    out = await ask_gemini_pro_latest("hi")
    assert "pro latest reply" in out
    assert route.called, "the pro-latest model URL was never actually requested"


def test_upper_tier_tools_registered_in_server():
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    for required in {"ask_cerebras_qwen", "ask_gemini_latest", "ask_gemini_pro_latest"}:
        assert required in names, f"missing tool: {required}"
