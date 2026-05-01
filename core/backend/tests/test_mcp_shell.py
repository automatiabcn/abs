"""MCP sunucu shell ve tool registry."""

from __future__ import annotations


def test_mcp_endpoint_reachable(client):
    # MCP endpoint GET'e 405/4xx döner (streamable-http POST ile protokol konuşur),
    # ama route mevcut olduğu için 404 DEĞİL — mount'un çalıştığının kanıtı.
    r = client.get("/mcp", follow_redirects=False)
    assert r.status_code != 404, f"/mcp mount edilmemiş — got {r.status_code}"
    assert r.status_code in (200, 307, 308, 400, 405, 406)


def test_tool_registry_has_10_tools():
    from app.mcp.server import mcp_server

    # FastMCP 1.x: tool listesi alınır
    import asyncio

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "ask_groq_fast",
        "ask_scout",
        "ask_cerebras",
        "ask_gemini",
        "ask_gemini_pro",
        "ask_cf",
        "ask_cf_gptoss",
        "ask_kimi",
        "ask_phi4",
        "system_status",
    }
    assert expected <= names, f"eksik tool'lar: {expected - names}"


def test_system_status_returns_structured_dict():
    import asyncio

    from app.mcp.tools.system import system_status

    # FastMCP 1.x: @tool() decorator orijinal coroutine'i korur
    result = asyncio.run(system_status())
    assert result["product"] == "Automatia ABS"
    assert "providers" in result
    assert "cache" in result
    assert "license" in result
    assert "configured" in result["providers"]
    assert set(result["providers"]["configured"].keys()) >= {
        "groq", "cerebras", "gemini", "cloudflare", "anthropic", "cohere", "ollama"
    }
