"""Provider client'ları — respx mock ile response parsing."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import settings
from app.providers.cerebras import CerebrasProvider
from app.providers.cloudflare import CloudflareProvider
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.providers.schemas import ProviderError


@pytest.mark.asyncio
@respx.mock
async def test_groq_parses_openai_response(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "sk-test")
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "Yanıt: 4"}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
        )
    )
    r = await GroqProvider().call("2+2?", model="llama-3.1-8b-instant")
    assert r.text == "Yanıt: 4"
    assert r.provider == "groq"
    assert r.tokens_in == 10
    assert r.tokens_out == 3


@pytest.mark.asyncio
async def test_groq_missing_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "")
    with pytest.raises(ProviderError) as e:
        await GroqProvider().call("hi")
    assert not e.value.transient


@pytest.mark.asyncio
@respx.mock
async def test_cerebras_parses_openai_response(monkeypatch):
    monkeypatch.setattr(settings, "cerebras_api_key", "sk-test")
    respx.post("https://api.cerebras.ai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "tamam"}}
                ]
            },
        )
    )
    r = await CerebrasProvider().call("ping")
    assert r.text == "tamam"
    assert r.provider == "cerebras"


@pytest.mark.asyncio
@respx.mock
async def test_cloudflare_parses_result_response(monkeypatch):
    monkeypatch.setattr(settings, "cf_account_id", "acc1")
    monkeypatch.setattr(settings, "cf_api_token", "tok1")
    respx.post(
        "https://api.cloudflare.com/client/v4/accounts/acc1/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": {"response": "edge cevap"},
            },
        )
    )
    r = await CloudflareProvider().call("merhaba")
    assert r.text == "edge cevap"
    assert r.provider == "cloudflare"


@pytest.mark.asyncio
@respx.mock
async def test_gemini_parses_candidates_response(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "key")
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "Merhaba dünya"}]}}
                ],
                "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 3},
            },
        )
    )
    r = await GeminiProvider().call("selam")
    assert r.text == "Merhaba dünya"
    assert r.tokens_in == 2
    assert r.tokens_out == 3


@pytest.mark.asyncio
@respx.mock
async def test_groq_5xx_raises_transient(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "sk-test")
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(ProviderError) as e:
        await GroqProvider().call("hi")
    assert e.value.transient is True
