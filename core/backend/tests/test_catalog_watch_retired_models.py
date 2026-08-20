"""The retirement watch: a pinned model that leaves the provider's catalogue is
announced by name, not discovered by a silent feature.

Background (2026-08-18 audit): Groq retired llama-3.x / qwen3-32b / kimi on
08-16. The product pinned those ids in 15 files; Tab was empty and
`ask_groq_fast` 404'd for two days while every panel said "groq · ready".
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.providers import catalog_watch as cw

# Names Groq retired on 2026-08-16. If any of these is pinned again the
# product is back where the audit found it.
RETIRED_GROQ = {
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "qwen/qwen3-32b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "moonshotai/kimi-k2-instruct",
}


def test_no_retired_groq_model_is_pinned_anywhere():
    pins = cw.pinned_models()
    assert pins.get("groq"), "the watch must know groq's pins"
    assert not (pins["groq"] & RETIRED_GROQ), pins["groq"] & RETIRED_GROQ


def test_the_registry_gathers_the_real_pinning_sites():
    """The registry reads the pins from the code, so it cannot drift from it."""
    from app.fim.complete import _FAST_MODELS
    from app.judge.senior import _JUDGE_ROUTES
    from app.providers.groq.adapter import DEFAULT_MODEL

    pins = cw.pinned_models()
    assert DEFAULT_MODEL in pins["groq"]
    assert _FAST_MODELS["groq"] in pins["groq"]
    for prov, model in _JUDGE_ROUTES:
        assert model in pins[prov]


def _listing(ids, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={"error": "nope"})
        return httpx.Response(200, json={"data": [{"id": i} for i in ids]})

    return httpx.MockTransport(handler)


@pytest.fixture
def mock_listing(monkeypatch):
    def install(ids, status=200):
        transport = _listing(ids, status)
        real = httpx.AsyncClient

        def fake_client(*a, **k):
            k["transport"] = transport
            return real(*a, **k)

        monkeypatch.setattr(cw.httpx, "AsyncClient", fake_client)

    return install


@pytest.mark.asyncio
async def test_a_retired_pin_is_reported_by_name(mock_listing):
    mock_listing(["openai/gpt-oss-20b", "qwen/qwen3.6-27b"])
    v = await cw.check_provider(
        "groq", ["openai/gpt-oss-20b", "llama-3.1-8b-instant"], api_key="k"
    )
    assert v.status == "retired"
    assert v.missing == ["llama-3.1-8b-instant"]
    assert v.live_count == 2


@pytest.mark.asyncio
async def test_all_pins_present_is_ok(mock_listing):
    mock_listing(["openai/gpt-oss-20b", "qwen/qwen3.6-27b"])
    v = await cw.check_provider("groq", ["qwen/qwen3.6-27b"], api_key="k")
    assert v.status == "ok"
    assert v.missing == []


@pytest.mark.asyncio
async def test_an_unreachable_listing_is_unknown_not_fine_and_not_retired(mock_listing):
    """A 500 from the catalogue says nothing about our pins."""
    mock_listing([], status=500)
    v = await cw.check_provider("groq", ["openai/gpt-oss-20b"], api_key="k")
    assert v.status == "unknown"
    assert v.missing == []
    assert "500" in v.detail


@pytest.mark.asyncio
async def test_no_key_means_no_verdict():
    v = await cw.check_provider("groq", ["openai/gpt-oss-20b"], api_key="")
    assert v.status == "no_key"


@pytest.mark.asyncio
async def test_a_provider_without_a_listing_says_unchecked():
    v = await cw.check_provider("cloudflare", ["@cf/x"], api_key="k")
    assert v.status == "unchecked"
    assert "listing" in v.detail


@pytest.mark.asyncio
async def test_run_once_remembers_and_persists(monkeypatch, tmp_path, mock_listing):
    mock_listing(["openai/gpt-oss-20b"])
    monkeypatch.setattr(cw, "_state_path", lambda: str(tmp_path / "cw.json"))
    monkeypatch.setattr(
        cw, "pinned_models", lambda: {"groq": {"openai/gpt-oss-20b", "gone-model"}}
    )
    monkeypatch.setattr(cw, "_LAST", {})
    from app.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "k", raising=False)
    out = await cw.run_once()
    assert out["groq"].status == "retired"
    assert cw.retired_models("groq") == ["gone-model"]
    on_disk = json.loads((tmp_path / "cw.json").read_text())
    assert on_disk["groq"]["missing"] == ["gone-model"]
    # A fresh process reads yesterday's verdict instead of claiming ignorance.
    monkeypatch.setattr(cw, "_LAST", {})
    assert cw.retired_models("groq") == ["gone-model"]


def test_retired_models_is_empty_when_unknown(monkeypatch, tmp_path):
    """Unknown ≠ retired: the bar must not paint a provider red on a guess."""
    monkeypatch.setattr(cw, "_state_path", lambda: str(tmp_path / "none.json"))
    monkeypatch.setattr(cw, "_LAST", {"groq": cw.ProviderVerdict("groq", "unknown")})
    assert cw.retired_models("groq") == []
