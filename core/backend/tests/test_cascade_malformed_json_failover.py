# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""3rd-eye audit — malformed-JSON 2xx must fail over, not crash the cascade.

The Gemini and CloudFlare adapters called `r.json()` outside any guard, unlike
base.py (OpenAI-compat) which wraps it. A 2xx response with a malformed body
raised a bare json.JSONDecodeError (ValueError) — NOT a ProviderError and NOT
in the orchestrator's _TRANSIENT_INFRA_EXCEPTIONS — so it propagated past the
cascade as an unhandled 500 instead of failing over to the next provider.

Both adapters now raise ProviderError(transient=True) on a parse error, so the
orchestrator routes to the next provider (graceful degradation contract).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.providers.base import ProviderError


@respx.mock
def test_gemini_malformed_json_raises_transient_provider_error(monkeypatch) -> None:
    from app.providers.gemini.adapter import GeminiProvider

    monkeypatch.setattr(
        "app.providers.gemini.adapter.settings.gemini_api_key",
        "AIzaSyTEST",
        raising=False,
    )
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    ).mock(return_value=httpx.Response(200, content=b"<<<not json>>>"))

    with pytest.raises(ProviderError) as ei:
        asyncio.run(GeminiProvider().call("merhaba"))
    assert ei.value.transient is True


@respx.mock
def test_cloudflare_malformed_json_raises_transient_provider_error(monkeypatch) -> None:
    from app.providers.cloudflare import CloudflareProvider

    monkeypatch.setattr(
        "app.providers.cloudflare.settings.cf_account_id", "acct123", raising=False
    )
    monkeypatch.setattr(
        "app.providers.cloudflare.settings.cf_api_token", "cftoken", raising=False
    )
    provider = CloudflareProvider()
    model = provider.default_model
    respx.post(
        f"https://api.cloudflare.com/client/v4/accounts/acct123/ai/run/{model}"
    ).mock(return_value=httpx.Response(200, content=b"<<<not json>>>"))

    with pytest.raises(ProviderError) as ei:
        asyncio.run(provider.call("merhaba"))
    assert ei.value.transient is True


@respx.mock
def test_ollama_malformed_json_raises_transient_provider_error(monkeypatch) -> None:
    """Same class as gemini/cloudflare: ollama called r.json() unguarded, so a
    2xx with a malformed body crashed the cascade instead of failing over."""
    from app.providers.ollama import OllamaProvider

    monkeypatch.setattr(
        "app.providers.ollama.settings.ollama_url",
        "http://ollama.local:11434",
        raising=False,
    )
    respx.post("http://ollama.local:11434/api/chat").mock(
        return_value=httpx.Response(200, content=b"<<<not json>>>")
    )

    with pytest.raises(ProviderError) as ei:
        asyncio.run(OllamaProvider().call("merhaba"))
    assert ei.value.transient is True


def test_cohere_malformed_response_raises_transient_not_empty(monkeypatch) -> None:
    """The cohere adapter swallowed a bad response shape into an empty success,
    which the cascade would record_success() + cache. A malformed response
    (here resp.message is None) must raise ProviderError(transient=True) so the
    cascade fails over instead of caching an empty answer."""
    from app.providers.cohere.adapter import CohereProvider

    monkeypatch.setattr(
        "app.providers.cohere.adapter.settings.cohere_api_key",
        "co-test",
        raising=False,
    )

    class _FakeResp:
        message = None  # `resp.message.content` → AttributeError

    class _FakeClient:
        def __init__(self, *a, **k) -> None:  # noqa: D401
            pass

        async def chat(self, **kwargs):
            return _FakeResp()

    import cohere

    monkeypatch.setattr(cohere, "AsyncClientV2", _FakeClient, raising=False)

    with pytest.raises(ProviderError) as ei:
        asyncio.run(CohereProvider().call("merhaba"))
    assert ei.value.transient is True
