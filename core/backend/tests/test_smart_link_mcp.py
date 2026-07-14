"""smart_link_status + provider_validate MCP tools."""

from __future__ import annotations

import asyncio
import json

import httpx

from app.smart_link.vault_secrets import _CACHE, encrypt_secret


def test_smart_link_status_lists_connected():
    _CACHE.clear()
    encrypt_secret(key_name="mcp_status_test", provider="openai", value="sk-mcp-12345")
    from app.mcp.tools.smart_link_tools import smart_link_status

    raw = asyncio.run(smart_link_status())
    out = json.loads(raw)
    assert "connected" in out
    assert "count" in out
    providers = {c["provider"] for c in out["connected"]}
    assert "openai" in providers


def test_provider_validate_via_mcp(monkeypatch):
    real_get = httpx.Client.get

    class _FakeRsp:
        status_code = 200

        def json(self):
            return {"data": []}

    def _get(self, url, *args, **kwargs):
        if "openai.com" in str(url):
            return _FakeRsp()
        return real_get(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "get", _get)

    from app.mcp.tools.smart_link_tools import provider_validate

    raw = asyncio.run(provider_validate("openai", "sk-mcp-test"))
    out = json.loads(raw)
    assert out["ok"] is True
    assert out["error"] is None


def test_provider_validate_unknown_returns_error():
    from app.mcp.tools.smart_link_tools import provider_validate

    raw = asyncio.run(provider_validate("unknown_xyz", "x" * 16))
    out = json.loads(raw)
    assert out["ok"] is False
    assert "Unknown provider" in out["error"]
