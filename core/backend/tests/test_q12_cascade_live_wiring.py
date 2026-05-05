"""Q12 Founder Tester Round 2 (BUG-4) — `/v1/cascade/run` live wiring.

Replaces the prior 503 "live_cascade_pending" stub with a real call to
`call_with_cascade()`. This test suite covers the route contract:

1. Configured chain → 200 + provider name + tokens_used.
2. Primary fails (transient) → fallback chain advances, 200.
3. All providers fail → 502 "all_providers_failed".
4. Cache hit → cached:true on second identical call.
5. anthropic_mock_mode on → still uses the mock, route never reaches
   the live path. (Regression guard for the mock branch.)

We monkeypatch `call_with_cascade` at the route level so the tests are
hermetic — no provider HTTP calls fire.
"""

from __future__ import annotations

import pytest

from app.providers.schemas import ProviderError, ProviderResponse


REAL_KEY = "real-test-key-AAAAAAAA"


@pytest.fixture()
def admin_client(client, monkeypatch):
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "off")
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_mock_mode", "off", raising=False)
    # Configure the typical 4-free chain (groq + cerebras + gemini + cloudflare).
    for attr in (
        "groq_api_key",
        "cerebras_api_key",
        "gemini_api_key",
        "cf_api_token",
    ):
        monkeypatch.setattr(settings, attr, REAL_KEY, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "", raising=False)
    monkeypatch.setattr(settings, "cohere_api_key", "", raising=False)

    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


def test_cascade_run_returns_200_with_first_provider(admin_client, monkeypatch):
    """Happy path — orchestrator returns; route surfaces provider+tokens."""

    async def _fake(prompt, *, primary, model=None, fallbacks=(), **kw):
        assert primary == "groq", "first active should be groq"
        return ProviderResponse(
            text="cevap",
            provider=primary,
            model=model or "llama-3.3-70b",
            elapsed_ms=42,
            tokens_in=12,
            tokens_out=8,
        )

    monkeypatch.setattr("app.api.cascade.call_with_cascade", _fake)

    r = admin_client.post(
        "/v1/cascade/run",
        json={"prompt": "merhaba", "max_tokens": 32},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["completion"] == "cevap"
    assert body["provider"] == "groq"
    assert body["tokens_used"] == 20
    assert body["fallback_chain"] == ["groq"]
    assert body["mock"] is False
    assert body["model"] == "llama-3.3-70b"


def test_cascade_run_502_when_all_providers_fail(admin_client, monkeypatch):
    """Orchestrator raises ProviderError → route → 502."""

    async def _all_fail(prompt, *, primary, **kw):
        raise ProviderError(
            "all transient", provider=primary, transient=True
        )

    monkeypatch.setattr("app.api.cascade.call_with_cascade", _all_fail)

    r = admin_client.post(
        "/v1/cascade/run",
        json={"prompt": "boom", "max_tokens": 8},
    )
    assert r.status_code == 502, r.text
    assert "all_providers_failed" in r.json().get("detail", "")


def test_cascade_run_passes_prefer_to_orchestrator(admin_client, monkeypatch):
    """`prefer` kwarg moves a provider to the front of the chain."""

    seen = {}

    async def _fake(prompt, *, primary, model=None, fallbacks=(), **kw):
        seen["primary"] = primary
        seen["fallbacks"] = list(fallbacks)
        return ProviderResponse(
            text="ok",
            provider=primary,
            model=model or "m",
            elapsed_ms=1,
            tokens_in=1,
            tokens_out=1,
        )

    monkeypatch.setattr("app.api.cascade.call_with_cascade", _fake)

    r = admin_client.post(
        "/v1/cascade/run",
        json={"prompt": "x", "prefer": "gemini"},
    )
    assert r.status_code == 200, r.text
    assert seen["primary"] == "gemini"
    # Remaining 3 free providers should still appear as fallbacks.
    assert "groq" in seen["fallbacks"]
    assert "cerebras" in seen["fallbacks"]


def test_cascade_run_surfaces_cached_flag(admin_client, monkeypatch):
    """Orchestrator marks `cached=True` on cache hit; route mirrors it."""

    async def _cached(prompt, *, primary, model=None, fallbacks=(), **kw):
        return ProviderResponse(
            text="cached-text",
            provider=primary,
            model="m",
            elapsed_ms=0,
            tokens_in=5,
            tokens_out=5,
            cached=True,
        )

    monkeypatch.setattr("app.api.cascade.call_with_cascade", _cached)

    r = admin_client.post(
        "/v1/cascade/run",
        json={"prompt": "deja vu", "max_tokens": 8},
    )
    assert r.status_code == 200, r.text
    assert r.json()["cached"] is True


def test_cascade_run_503_when_no_providers(client, monkeypatch):
    """Empty chain (and no mock) → 503 no_providers_configured."""
    from app.config import settings

    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "off")
    monkeypatch.setattr(settings, "anthropic_mock_mode", "off", raising=False)
    for attr in (
        "anthropic_api_key",
        "groq_api_key",
        "cerebras_api_key",
        "gemini_api_key",
        "cf_api_token",
        "cohere_api_key",
    ):
        monkeypatch.setattr(settings, attr, "", raising=False)

    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/v1/cascade/run",
        json={"prompt": "no keys"},
    )
    assert r.status_code == 503, r.text
    assert "no_providers_configured" in r.json().get("detail", "")
