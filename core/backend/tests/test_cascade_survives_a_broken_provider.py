# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""One misconfigured provider is not an outage.

Found by running the agent scenarios against a real server. The install had a
perfectly good Groq key and a Cloudflare section still holding the sample
account id from .env.example. Cloudflare therefore counted as "configured",
sorted first in the free-first chain, and answered every call with a 404. A 404
is a *permanent* error, and the orchestrator raised on permanent errors — so the
chain aborted before Groq was ever tried, and all seven approval-gated agents
degraded to "no provider available" while a working provider sat second in line.

Nothing errored loudly. The agents just quietly stopped proposing anything.

Two defences, tested here: a half-configured provider does not join the chain at
all, and a provider that fails for any reason hands off to the next one instead
of taking the cascade down with it.
"""

from __future__ import annotations

import pytest

from app.providers import cascade as cascade_mod
from app.providers.schemas import ProviderError, ProviderResponse


class TestHalfConfiguredProvidersStayOut:
    def test_the_sample_account_id_does_not_count_as_configured(self, monkeypatch):
        # Exactly what .env.example ships. It is long enough to pass a length
        # check, which is why the old check let it through.
        monkeypatch.setattr(cascade_mod.settings, "cf_api_token", "a-real-looking-token-value")
        monkeypatch.setattr(cascade_mod.settings, "cf_account_id", "replace-with-cf-account-id")
        assert cascade_mod.is_configured("cloudflare") is False

    def test_a_token_without_an_account_id_routes_nowhere(self, monkeypatch):
        monkeypatch.setattr(cascade_mod.settings, "cf_api_token", "a-real-looking-token-value")
        monkeypatch.setattr(cascade_mod.settings, "cf_account_id", "")
        assert cascade_mod.is_configured("cloudflare") is False

    def test_both_halves_present_is_configured(self, monkeypatch):
        monkeypatch.setattr(cascade_mod.settings, "cf_api_token", "a-real-looking-token-value")
        monkeypatch.setattr(cascade_mod.settings, "cf_account_id", "0123456789abcdef0123456789abcdef")
        assert cascade_mod.is_configured("cloudflare") is True

    def test_placeholder_keys_are_refused_however_long_they_are(self, monkeypatch):
        for placeholder in (
            "replace-with-groq-key",
            "CHANGEME-this-is-not-a-key",
            "your-key-goes-here",
        ):
            monkeypatch.setattr(cascade_mod.settings, "groq_api_key", placeholder)
            assert cascade_mod.is_configured("groq") is False, placeholder

    def test_a_real_key_still_configures_the_provider(self, monkeypatch):
        monkeypatch.setattr(cascade_mod.settings, "groq_api_key", "gsk_liveKeyThatIsLongEnough")
        assert cascade_mod.is_configured("groq") is True

    def test_a_broken_provider_is_absent_from_the_chain_entirely(self, monkeypatch):
        monkeypatch.setattr(cascade_mod.settings, "groq_api_key", "gsk_liveKeyThatIsLongEnough")
        monkeypatch.setattr(cascade_mod.settings, "cf_api_token", "a-real-looking-token-value")
        monkeypatch.setattr(cascade_mod.settings, "cf_account_id", "replace-with-cf-account-id")
        for attr in ("anthropic_api_key", "gemini_api_key", "cerebras_api_key", "cohere_api_key"):
            monkeypatch.setattr(cascade_mod.settings, attr, "")

        assert cascade_mod.get_active_providers() == ["groq"]


class TestOneProviderFailingIsNotEveryProviderFailing:
    @pytest.mark.asyncio
    async def test_a_permanent_failure_hands_off_to_the_next_provider(self, monkeypatch):
        from app.cascade import orchestrator

        calls: list[str] = []

        class Dead:
            async def call(self, prompt, model=None, **kwargs):
                calls.append("dead")
                # A 404 from a misrouted account: permanent, and none of the
                # next provider's business.
                raise ProviderError("CloudFlare 404: could not route", provider="cloudflare", transient=False)

        class Alive:
            async def call(self, prompt, model=None, **kwargs):
                calls.append("alive")
                return ProviderResponse(
                    text="the answer", provider="groq", model="m", tokens_used=3, latency_ms=1
                )

        monkeypatch.setattr(
            orchestrator, "get_provider", lambda name: Dead() if name == "cloudflare" else Alive()
        )

        resp = await orchestrator.call_with_cascade(
            "anything", primary="cloudflare", fallbacks=("groq",), use_cache=False
        )

        assert resp.text == "the answer"
        assert calls == ["dead", "alive"]  # it did not stop at the corpse

    @pytest.mark.asyncio
    async def test_when_every_provider_is_misconfigured_the_error_says_so(self, monkeypatch):
        # Nothing here gets better by waiting, so the caller must not be told to
        # retry in sixty seconds. It gets the provider's own error — which names
        # what is wrong, and which the callers that degrade gracefully on a bad
        # key already catch.
        from app.cascade import orchestrator

        class Dead:
            def __init__(self, why: str) -> None:
                self.why = why

            async def call(self, prompt, model=None, **kwargs):
                raise ProviderError(self.why, provider="x", transient=False)

        monkeypatch.setattr(
            orchestrator,
            "get_provider",
            lambda name: Dead(f"{name} is misconfigured: bad account id"),
        )

        with pytest.raises(ProviderError, match="misconfigured"):
            await orchestrator.call_with_cascade(
                "anything", primary="cloudflare", fallbacks=("groq",), use_cache=False
            )

    @pytest.mark.asyncio
    async def test_when_everyone_is_merely_down_the_caller_is_told_to_retry(self, monkeypatch):
        from fastapi import HTTPException

        from app.cascade import orchestrator

        class RateLimited:
            async def call(self, prompt, model=None, **kwargs):
                raise ProviderError("rate limit", provider="x", transient=True)

        monkeypatch.setattr(orchestrator, "get_provider", lambda name: RateLimited())

        with pytest.raises(HTTPException) as caught:
            await orchestrator.call_with_cascade(
                "anything", primary="groq", fallbacks=("gemini",), use_cache=False
            )

        assert caught.value.status_code == 503
        assert caught.value.detail["providers_tried"] == ["groq", "gemini"]
        # "ProviderError" alone tells an operator nothing; the message does.
        assert "rate limit" in caught.value.detail["last_error"]
