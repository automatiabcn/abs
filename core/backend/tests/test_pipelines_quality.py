"""Quality pipeline tests — with provider mock."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.pipelines import quality as q
from app.pipelines.base import PipelineResult
from app.providers.schemas import ProviderError, ProviderResponse


def _make_resp(
    text: str, model: str = "m", provider: str = "p", elapsed: int = 100
) -> ProviderResponse:
    return ProviderResponse(
        text=text, model=model, provider=provider, elapsed_ms=elapsed
    )


@pytest.fixture
def fake_providers(monkeypatch):
    """All get_provider calls should return an AsyncMock provider."""
    providers = {}

    def _set(
        name: str,
        responses: dict[str, ProviderResponse] | None = None,
        raise_for: set[str] | None = None,
    ):
        mock = AsyncMock()

        async def _call(prompt, model=None, **kw):
            if raise_for and model in raise_for:
                raise ProviderError("fake", provider=name, transient=True)
            if responses and model in responses:
                return responses[model]
            # generic success
            return _make_resp(
                f"{name}:{(model or 'default')}:{prompt[:20]}",
                model=model or "?",
                provider=name,
            )

        mock.call = _call
        providers[name] = mock
        return mock

    import app.pipelines.quality.analysis as qa
    import app.pipelines.quality.code as qc
    import app.pipelines.quality.translate as qt
    import app.pipelines.quality.turkish as qtr

    def _get(name):
        return providers.get(name) or _set(name)

    for mod in (qc, qtr, qa, qt):
        monkeypatch.setattr(mod, "get_provider", _get)

    return _set


@pytest.mark.asyncio
async def test_qual_code_chain_all_pass(fake_providers):
    fake_providers(
        "cloudflare", {"@cf/moonshotai/kimi-k2.5": _make_resp("def foo(): return 1")}
    )
    fake_providers("groq", {"openai/gpt-oss-20b": _make_resp("def foo(): return 2")})
    fake_providers("ollama", {"codellama:7b": _make_resp("PASS")})

    result = await q.QualCodePipeline().run("Fibonacci fonksiyonu yaz")
    assert isinstance(result, PipelineResult)
    assert result.pipeline_type == "qual-code"
    assert result.error is None
    # "PASS" → skip the fix step
    names = [s.name for s in result.steps]
    assert "parallel-drafts" in names
    assert "verify" in names
    assert "fix" not in names
    assert result.final_response  # boş değil


@pytest.mark.asyncio
async def test_qual_code_triggers_fix_when_verify_finds_issues(fake_providers):
    fake_providers(
        "cloudflare", {"@cf/moonshotai/kimi-k2.5": _make_resp("def foo(): return 1")}
    )
    fake_providers(
        "groq",
        {
            "openai/gpt-oss-20b": _make_resp("def foo(): return 2"),
            "openai/gpt-oss-120b": _make_resp("def foo():\n    return 1  # fixed"),
        },
    )
    fake_providers(
        "ollama", {"codellama:7b": _make_resp("Missing type hint on return")}
    )

    result = await q.QualCodePipeline().run("tip ipuçlu fonksiyon")
    names = [s.name for s in result.steps]
    assert "fix" in names
    assert "fixed" in result.final_response


@pytest.mark.asyncio
async def test_qual_tr_chain_passes_review(fake_providers):
    fake_providers("groq", {"qwen/qwen3-32b": _make_resp("Uzun Türkçe metin bu.")})
    fake_providers(
        "gemini", {"gemini-2.5-flash": _make_resp("Alternatif metin çok kısa")}
    )
    fake_providers("ollama", {"aya:8b": _make_resp("TAMAM")})
    fake_providers("cloudflare")

    result = await q.QualTrPipeline().run("React nedir açıkla")
    assert result.pipeline_type == "qual-tr"
    names = [s.name for s in result.steps]
    assert "parallel-drafts" in names
    assert "review" in names
    assert "polish" not in names  # TAMAM → polish skip


@pytest.mark.asyncio
async def test_qual_analysis_synthesizes_3_perspectives(fake_providers):
    fake_providers(
        "groq",
        {
            "openai/gpt-oss-120b": _make_resp("SENTEZ: hepsi iyi"),
        },
    )
    # override: in perspective call technical = gptoss, in synthesis also gptoss
    # because the mock is simple it will always return "SENTEZ: all good"; that's OK
    fake_providers(
        "cloudflare", {"@cf/moonshotai/kimi-k2.5": _make_resp("stratejik perspektif")}
    )
    fake_providers("gemini", {"gemini-2.5-pro": _make_resp("kritik perspektif")})

    result = await q.QualAnalysisPipeline().run("Self-hosted AI sistemi mi, cloud mu?")
    names = [s.name for s in result.steps]
    assert "3-perspectives" in names
    assert "synthesis" in names
    assert "SENTEZ" in result.final_response


@pytest.mark.asyncio
async def test_qual_translate_roundtrip(fake_providers):
    fake_providers("groq", {"qwen/qwen3-32b": _make_resp("Merhaba dünya")})
    fake_providers(
        "cloudflare", {"@cf/moonshotai/kimi-k2.5": _make_resp("Hello world")}
    )
    fake_providers("ollama", {"llama3.1:8b": _make_resp("TAMAM")})

    result = await q.QualTranslatePipeline().run("Hello world")
    assert result.pipeline_type == "qual-translate"
    names = [s.name for s in result.steps]
    assert "translate" in names
    assert "back-translate" in names
    assert "compare" in names
    assert "refine" not in names  # TAMAM → refine skip
    assert result.final_response == "Merhaba dünya"
