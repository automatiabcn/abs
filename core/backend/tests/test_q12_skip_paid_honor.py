"""Q12 Founder Tester Round 3 (BUG-7 + BUG-8) — `skip_paid_providers` honor.

Source: founder Playwright quality v2 session (2026-05-05). 8 cascade tasks
were issued with `skip_paid_providers:true`; all 8 routed to Anthropic
Claude haiku-4.5 (paid path), provider mix `{"anthropic": 8}`. Cost
savings = 0.

Root cause: `app/providers/cascade.get_active_providers` ignored the flag.
The Pydantic body schema didn't expose it either.

This test guards three contracts:

* BUG-7  `skip_paid=True`  → no paid provider in routing, even when
                              `anthropic_api_key` is set.
* BUG-7  `skip_paid=False` → anthropic stays primary (default behavior
                              for ops who supplied a paid key).
* BUG-7  `skip_paid=True` + only paid keys → 503 "no_free_providers" so
                              the panel can prompt the operator to
                              configure at least one free provider.
* BUG-8  Free chain starts with `groq` (Llama 3.3 70B + GPT-OSS 120B
                              best free quality).

We monkeypatch `call_with_cascade` so the route stays hermetic.
"""

from __future__ import annotations

import pytest

from app.providers.cascade import (
    PAID_PROVIDERS,
    PROVIDER_ORDER_FREE_FIRST,
    PROVIDER_ORDER_PAID_FIRST,
    get_active_providers,
)
from app.providers.schemas import ProviderResponse


REAL_KEY = "real-test-key-AAAAAAAA"


@pytest.fixture()
def all_keys_admin(client, monkeypatch):
    """Login + every provider configured (incl. anthropic). Default behaviour
    routes to anthropic; skip_paid=True must reroute to free chain."""
    from app.config import settings

    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "off")
    monkeypatch.setattr(settings, "anthropic_mock_mode", "off", raising=False)
    for attr in (
        "anthropic_api_key",
        "groq_api_key",
        "cerebras_api_key",
        "gemini_api_key",
        "cf_api_token",
        "cf_account_id",
        "cohere_api_key",
    ):
        monkeypatch.setattr(settings, attr, REAL_KEY, raising=False)

    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def paid_only_admin(client, monkeypatch):
    """Login + only anthropic configured. skip_paid=True must 503."""
    from app.config import settings

    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "off")
    monkeypatch.setattr(settings, "anthropic_mock_mode", "off", raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", REAL_KEY, raising=False)
    for attr in (
        "groq_api_key",
        "cerebras_api_key",
        "gemini_api_key",
        "cf_api_token",
        "cf_account_id",
        "cohere_api_key",
    ):
        monkeypatch.setattr(settings, attr, "", raising=False)

    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


# ---------- unit-level: ordering + filtering ----------------------------


def test_paid_first_chain_unchanged_default():
    """Default chain begins with anthropic (paid first, quality first)."""
    assert PROVIDER_ORDER_PAID_FIRST[0] == "anthropic"
    assert "anthropic" in PROVIDER_ORDER_PAID_FIRST


def test_free_first_chain_groq_leads_no_paid():
    """BUG-8 — free-first chain starts with groq, contains zero paid."""
    assert PROVIDER_ORDER_FREE_FIRST[0] == "groq"
    assert not (set(PROVIDER_ORDER_FREE_FIRST) & PAID_PROVIDERS), (
        "free-first chain must not contain paid providers, got "
        f"{set(PROVIDER_ORDER_FREE_FIRST) & PAID_PROVIDERS}"
    )


def test_get_active_providers_default_free_first_anthropic_last(monkeypatch):
    """Default (skip_paid=False) is free-first with anthropic as the last-resort
    premium fallback (PROVIDER_ORDER_DEFAULT, per ABS_HYBRID_TIER_PROMISE);
    skip_paid=True drops anthropic entirely and stays groq-first."""
    from app.config import settings

    for attr in (
        "anthropic_api_key",
        "groq_api_key",
        "cerebras_api_key",
        "gemini_api_key",
        "cf_api_token",
        "cf_account_id",
        "cohere_api_key",
    ):
        monkeypatch.setattr(settings, attr, REAL_KEY, raising=False)

    default = get_active_providers(skip_paid=False)
    free = get_active_providers(skip_paid=True)

    # Free-first: groq leads, anthropic present but last (quota-protected lane).
    assert default[0] == "groq", default
    assert default[-1] == "anthropic", default
    assert "anthropic" not in free, free
    assert free[0] == "groq", free
    # All 5 free providers configured + ordered.
    assert set(free) == set(PROVIDER_ORDER_FREE_FIRST)


# ---------- route-level: HTTP contract --------------------------------


def test_cascade_skip_paid_routes_to_free_provider(all_keys_admin, monkeypatch):
    """BUG-7 — 8 prompts × skip_paid=true, none routed to anthropic.

    Mirrors the founder Playwright quality v2 session (8/8 anthropic before
    fix). Post-fix the route must pick a free provider every time.
    """
    routed: list[str] = []

    async def _capture(prompt, *, primary, model=None, fallbacks=(), **kw):
        routed.append(primary)
        return ProviderResponse(
            text=f"free:{primary}",
            provider=primary,
            model=model or "free-model",
            elapsed_ms=10,
            tokens_in=2,
            tokens_out=3,
        )

    monkeypatch.setattr("app.api.cascade.call_with_cascade", _capture)

    # Reproduce the 8-task footprint from the founder session.
    prompts = [
        "simple_tr",
        "simple_en",
        "analysis",
        "code",
        "reasoning",
        "translation",
        "long_context",
        "classification",
    ]
    for prompt in prompts:
        r = all_keys_admin.post(
            "/v1/cascade/run",
            json={"prompt": prompt, "skip_paid_providers": True, "max_tokens": 8},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["provider"] not in PAID_PROVIDERS, (
            f"skip_paid honor failed: routed to {body['provider']!r} "
            f"(prompt={prompt!r})"
        )

    # Founder evidence: post-fix, 0/8 anthropic; primary = groq for every call
    # (orchestrator-level fail-over may shuffle in real env, but at the route
    # gate the *primary* is picked from the free chain).
    assert routed, "orchestrator was never invoked"
    assert all(p not in PAID_PROVIDERS for p in routed), routed
    assert routed[0] == "groq", f"free chain primary should be groq, got {routed[0]}"


def test_cascade_default_routes_to_free_primary_anthropic_last(
    all_keys_admin, monkeypatch
):
    """Default (skip_paid=False) is free-first — groq leads, anthropic stays in
    the chain only as the quota-protected last-resort fallback
    (ABS_HYBRID_TIER_PROMISE: "Free path first … 95%+ of the work on free")."""

    seen: dict = {}

    async def _capture(prompt, *, primary, model=None, fallbacks=(), **kw):
        seen["primary"] = primary
        seen["fallbacks"] = tuple(fallbacks)
        return ProviderResponse(
            text="free",
            provider=primary,
            model=model or "llama-3.3-70b",
            elapsed_ms=10,
            tokens_in=2,
            tokens_out=3,
        )

    monkeypatch.setattr("app.api.cascade.call_with_cascade", _capture)

    r = all_keys_admin.post(
        "/v1/cascade/run",
        json={"prompt": "default chain", "max_tokens": 8},
    )
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "groq"
    assert seen["primary"] == "groq", seen
    # Anthropic present but pushed to the very end of the fallback chain.
    assert seen["fallbacks"][-1] == "anthropic", seen


def test_cascade_skip_paid_no_free_providers_returns_503(paid_only_admin):
    """BUG-7 — skip_paid=true + only anthropic configured → 503 graceful."""
    r = paid_only_admin.post(
        "/v1/cascade/run",
        json={"prompt": "no free keys", "skip_paid_providers": True},
    )
    assert r.status_code == 503, r.text
    detail = r.json().get("detail", "")
    assert "no_free_providers_configured" in detail, detail
