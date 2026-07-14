"""Race pipeline tests — first success wins."""

from __future__ import annotations

import asyncio

import pytest

from app.pipelines.race.code import RaceCodePipeline
from app.pipelines.race.general import RaceGeneralPipeline
from app.providers.schemas import ProviderError, ProviderResponse


class _FakeProvider:
    def __init__(self, text: str, delay: float = 0.01, raise_exc: bool = False):
        self._text = text
        self._delay = delay
        self._raise = raise_exc

    async def call(self, prompt, model=None, **kw):
        await asyncio.sleep(self._delay)
        if self._raise:
            raise ProviderError("fail", provider="fake", transient=True)
        return ProviderResponse(
            text=f"{self._text}:{model}",
            model=model or "?",
            provider="fake",
            elapsed_ms=int(self._delay * 1000),
        )


@pytest.mark.asyncio
async def test_race_code_first_success_wins(monkeypatch):
    fast = _FakeProvider("fast", delay=0.01)
    slow = _FakeProvider("slow", delay=0.3)
    import app.pipelines.race.code as rc

    def _get(name):
        return fast if name == "cloudflare" else slow

    monkeypatch.setattr(rc, "get_provider", _get)
    result = await RaceCodePipeline().run("kod yaz")
    assert result.pipeline_type == "race-code"
    assert "fast" in result.final_response
    assert result.steps[0].meta.get("winner") == "cf-kimi"


@pytest.mark.asyncio
async def test_race_all_fail_returns_error(monkeypatch):
    failer = _FakeProvider("-", delay=0.01, raise_exc=True)
    import app.pipelines.race.general as rg

    monkeypatch.setattr(rg, "get_provider", lambda _: failer)
    result = await RaceGeneralPipeline().run("hiçbiri")
    assert result.error is not None
    assert result.final_response == ""
