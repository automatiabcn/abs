# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""A local model the operator installed has to be reachable.

Differentiator #5 in the pivot document is sovereignty: self-host, air-gap,
audit export. Audited 2026-08-02, the air-gapped half did not work at all.

`ollama` and `mlx` were absent from `SETTINGS_KEY_ATTR` and from every
`PROVIDER_ORDER_*`, so `is_configured` returned False for them no matter what
and `get_active_providers` could not return them even when asked to. A box with
a running Ollama and no internet had no assistant: the cascade found an empty
chain and returned 503. `app/cascade/ollama_first.py` — a whole module for the
local-first chain — had no callers at all.

It also broke the product's own promise for the ordinary case, which is the
part worth caring about commercially: whatever you bring, the system starts
working at that level. A local model is the one provider that needs no key, no
card and no signup, and it was the one the chain could not see.

The rules pinned here:

* a local provider counts as configured when its URL is set — that setting IS
  the operator saying the runtime exists, there is no key to check;
* it never appears in a chain that was not asked for it, so an install with no
  local runtime does not pay a connection timeout on every call;
* by default it sits after the free cloud tier and before anything paid: it
  costs nothing, so being asked before a paid provider is the whole point;
* with `ollama_first_enabled` it leads, which is what an air-gapped or
  privacy-first install actually wants.
"""

from __future__ import annotations

import pytest

from app.providers import cascade


@pytest.fixture
def local_only(monkeypatch):
    """A box with Ollama running and no cloud keys at all."""
    monkeypatch.setattr(cascade.settings, "ollama_url", "http://localhost:11434")
    for attr in (
        "groq_api_key",
        "cerebras_api_key",
        "gemini_api_key",
        "cohere_api_key",
        "cf_api_token",
        "anthropic_api_key",
        "openrouter_api_key",
        "mlx_url",
    ):
        monkeypatch.setattr(cascade.settings, attr, "", raising=False)
    monkeypatch.setattr(cascade.settings, "ollama_first_enabled", False, raising=False)


def test_a_local_runtime_counts_as_configured(local_only):
    assert cascade.is_configured("ollama") is True, (
        "the URL is the operator telling us the runtime exists; there is no "
        "key to look for"
    )


def test_an_air_gapped_install_has_an_assistant(local_only):
    chain = cascade.get_active_providers()
    assert chain, "a box with a working local model was told no provider exists"
    assert chain[0] == "ollama"


def test_a_cloud_install_does_not_get_a_dead_local_leg(monkeypatch):
    """Nobody pays a connection timeout for a runtime they never installed."""
    monkeypatch.setattr(cascade.settings, "ollama_url", "", raising=False)
    monkeypatch.setattr(cascade.settings, "mlx_url", "", raising=False)
    monkeypatch.setattr(cascade.settings, "groq_api_key", "gsk_a1b2c3d4e5a1b2c3d4e5a1b2c3d4e5")
    chain = cascade.get_active_providers()
    assert "ollama" not in chain
    assert "mlx" not in chain
    assert chain[0] == "groq"


def test_free_local_is_asked_before_anything_paid(monkeypatch):
    monkeypatch.setattr(cascade.settings, "ollama_url", "http://localhost:11434")
    monkeypatch.setattr(cascade.settings, "groq_api_key", "gsk_a1b2c3d4e5a1b2c3d4e5a1b2c3d4e5")
    monkeypatch.setattr(cascade.settings, "anthropic_api_key", "sk-ant-a1b2c3d4e5a1b2c3d4e5a1b2c3d4e5")
    monkeypatch.setattr(cascade.settings, "ollama_first_enabled", False, raising=False)
    chain = cascade.get_active_providers()
    assert chain.index("ollama") < chain.index("anthropic"), (
        "a provider that costs nothing was queued behind one that bills"
    )
    assert chain.index("groq") < chain.index("ollama"), (
        "a fast free cloud tier still leads by default — local is the cheaper "
        "fallback, not a speed regression forced on everyone"
    )


def test_ollama_first_puts_the_local_model_in_front(monkeypatch):
    monkeypatch.setattr(cascade.settings, "ollama_url", "http://localhost:11434")
    monkeypatch.setattr(cascade.settings, "groq_api_key", "gsk_a1b2c3d4e5a1b2c3d4e5a1b2c3d4e5")
    monkeypatch.setattr(cascade.settings, "ollama_first_enabled", True, raising=False)
    chain = cascade.get_active_providers()
    assert chain[0] == "ollama", (
        "the setting exists precisely so a private install can insist on local"
    )


def test_skip_paid_keeps_the_local_model(monkeypatch):
    """`skip_paid` is a cost decision. A local model is the cheapest thing here."""
    monkeypatch.setattr(cascade.settings, "ollama_url", "http://localhost:11434")
    monkeypatch.setattr(cascade.settings, "anthropic_api_key", "sk-ant-a1b2c3d4e5a1b2c3d4e5a1b2c3d4e5")
    chain = cascade.get_active_providers(skip_paid=True)
    assert "ollama" in chain
    assert "anthropic" not in chain


def test_mlx_is_reachable_the_same_way(monkeypatch):
    monkeypatch.setattr(cascade.settings, "mlx_url", "http://localhost:8080")
    monkeypatch.setattr(cascade.settings, "ollama_url", "", raising=False)
    assert cascade.is_configured("mlx") is True
    assert "mlx" in cascade.get_active_providers()
