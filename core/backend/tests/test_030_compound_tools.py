"""030 Modul D — Groq compound MCP tools (mocked)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.config import settings


def _stub_response(content: str = "ok") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        },
    )


@respx.mock
@pytest.mark.asyncio
async def test_ask_compound_returns_text(monkeypatch):
    from app.mcp.tools.compound_tools import ask_compound

    monkeypatch.setattr(settings, "groq_api_key", "sk-test")
    route = respx.post(
        "https://api.groq.com/openai/v1/chat/completions"
    ).mock(return_value=_stub_response("compound says hi"))
    out = await ask_compound("plan a trip")
    assert out == "compound says hi"
    assert route.called


@respx.mock
@pytest.mark.asyncio
async def test_ask_compound_mini_returns_text(monkeypatch):
    from app.mcp.tools.compound_tools import ask_compound_mini

    monkeypatch.setattr(settings, "groq_api_key", "sk-test")
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_stub_response("mini ok")
    )
    out = await ask_compound_mini("2+2")
    assert out == "mini ok"


@respx.mock
@pytest.mark.asyncio
async def test_ask_compound_uses_compound_model_name(monkeypatch):
    from app.mcp.tools.compound_tools import ask_compound

    monkeypatch.setattr(settings, "groq_api_key", "sk-test")
    captured: dict = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content.decode())
        return _stub_response("done")

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=_capture
    )
    await ask_compound("compound-model-uniqueness-probe")
    assert captured["body"]["model"] == "groq/compound"


@respx.mock
@pytest.mark.asyncio
async def test_ask_compound_max_tokens_default_is_2000(monkeypatch):
    from app.mcp.tools.compound_tools import ask_compound

    monkeypatch.setattr(settings, "groq_api_key", "sk-test")
    captured: dict = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content.decode())
        return _stub_response("ok")

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        side_effect=_capture
    )
    await ask_compound("compound-max-tokens-uniqueness-probe")
    assert captured["body"]["max_tokens"] == 2000


def test_compound_tools_registered_in_server():
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert "ask_compound" in names
    assert "ask_compound_mini" in names


@pytest.mark.asyncio
async def test_ask_compound_graceful_when_key_missing(monkeypatch):
    """No Groq key → tool returns [HATA] string, never raises."""
    from app.mcp.tools.compound_tools import ask_compound

    monkeypatch.setattr(settings, "groq_api_key", "")
    out = await ask_compound("compound-no-key-probe")
    assert isinstance(out, str)
    assert "[HATA]" in out
