"""news_digest MCP tool (mocked gemini search)."""

from __future__ import annotations

import pytest

from app.providers.schemas import ProviderResponse


@pytest.fixture(autouse=True)
def _wipe_cache(tmp_path, monkeypatch):
    """Point the cache file at a fresh tmp file per test."""
    from app.mcp.tools import news_digest as nd

    monkeypatch.setattr(nd, "CACHE_PATH", tmp_path / "news_cache.json")
    yield


def _ok(text: str) -> ProviderResponse:
    return ProviderResponse(text=text, provider="gemini", model="gemini-2.5-flash")


@pytest.mark.asyncio
async def test_news_digest_runs_5_parallel_queries(monkeypatch):
    from app.mcp.tools import news_digest as nd

    calls: list[str] = []

    async def fake_search(query: str):
        calls.append(query)
        return _ok(f"result for: {query}")

    monkeypatch.setattr(nd._gx, "gemini_search", fake_search)
    out = await nd.news_digest()
    assert "# News Digest" in out
    # 5 sections present
    for label in ("Anthropic", "OpenAI", "Gemini", "GitHub trending", "MCP"):
        assert f"## {label}" in out
    assert len(calls) == 5


@pytest.mark.asyncio
async def test_news_digest_cache_hit_skips_calls(monkeypatch, tmp_path):
    from app.mcp.tools import news_digest as nd

    monkeypatch.setattr(nd, "CACHE_PATH", tmp_path / "c.json")
    nd._write_cache("# News Digest\n\ncached body")

    async def explode(*_a, **_k):
        raise AssertionError("should not be called when cache valid")

    monkeypatch.setattr(nd._gx, "gemini_search", explode)
    out = await nd.news_digest()
    assert "cached body" in out


@pytest.mark.asyncio
async def test_news_digest_force_refresh_bypasses_cache(monkeypatch, tmp_path):
    from app.mcp.tools import news_digest as nd

    monkeypatch.setattr(nd, "CACHE_PATH", tmp_path / "c.json")
    nd._write_cache("# News Digest\n\nstale body")
    calls: list[str] = []

    async def fake_search(query: str):
        calls.append(query)
        return _ok(f"fresh: {query}")

    monkeypatch.setattr(nd._gx, "gemini_search", fake_search)
    out = await nd.news_digest(force_refresh=True)
    assert "fresh:" in out
    assert "stale body" not in out
    assert len(calls) == 5


@pytest.mark.asyncio
async def test_news_digest_writes_valid_json_cache(monkeypatch, tmp_path):
    """Cache file is parseable JSON with ts + markdown keys."""
    import json as _json

    from app.mcp.tools import news_digest as nd

    cache_path = tmp_path / "cache.json"
    monkeypatch.setattr(nd, "CACHE_PATH", cache_path)

    async def fake_search(query: str):
        return _ok(f"data for {query}")

    monkeypatch.setattr(nd._gx, "gemini_search", fake_search)
    await nd.news_digest()

    raw = _json.loads(cache_path.read_text())
    assert isinstance(raw["ts"], (int, float))
    assert raw["ts"] > 0
    assert "# News Digest" in raw["markdown"]


@pytest.mark.asyncio
async def test_news_digest_tolerates_query_failures(monkeypatch):
    from app.providers.schemas import ProviderError
    from app.mcp.tools import news_digest as nd

    async def flaky_search(query: str):
        if "OpenAI" in query:
            raise ProviderError("rate limited", provider="gemini", transient=True)
        return _ok(f"ok: {query}")

    monkeypatch.setattr(nd._gx, "gemini_search", flaky_search)
    out = await nd.news_digest()
    # Failed query gets an inline failure note; others succeed
    assert "## OpenAI" in out
    assert "query failed" in out
    assert "## Anthropic" in out
    assert "ok:" in out
