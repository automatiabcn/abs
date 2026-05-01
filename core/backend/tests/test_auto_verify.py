"""Auto-verify pipeline testleri — Ollama URL kontrolü."""

from __future__ import annotations

import pytest

from app.config import settings
from app.pipelines.verify.code import AutoVerifyCodePipeline
from app.pipelines.verify.turkish import AutoVerifyTurkishPipeline


@pytest.mark.asyncio
async def test_auto_verify_code_without_ollama_returns_error(monkeypatch):
    monkeypatch.setattr(settings, "ollama_url", "")
    result = await AutoVerifyCodePipeline().run("print('hi')")
    assert result.error is not None
    assert "OLLAMA_URL" in result.error
    assert result.steps[0].ok is False


@pytest.mark.asyncio
async def test_auto_verify_turkish_without_ollama_returns_error(monkeypatch):
    monkeypatch.setattr(settings, "ollama_url", "")
    result = await AutoVerifyTurkishPipeline().run("Merhaba dünya")
    assert result.error is not None
