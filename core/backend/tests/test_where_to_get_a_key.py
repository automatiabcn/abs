# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Telling somebody they need a key is half an instruction.

The product runs on the developer's own keys, so "add a provider key" is the
first thing a new install asks for — and until now the editor answered it from
its own hard-coded list, which said "free tier" and not *where*. The backend
already knew: `HOW_TO_GET` carries the console URL and whether a card is needed.

Two sources for the same fact drift, and the one that drifts is always the copy
nobody remembers exists. So the readout ships the map, and the editor's picker
reads it instead of keeping its own.

What is pinned:

* every provider a caller can be asked to bring is in the map — a picker entry
  with no instructions behind it is the exact gap this closes;
* free tiers are marked as free, because the cheapest unlock is the honest one
  to recommend and a picker that hides it sells an Anthropic key to somebody
  who needed Groq;
* the sentences are actionable — a domain to go to, not an adjective.
"""

from __future__ import annotations

import asyncio
import json

import app.mcp.server  # noqa: F401  (registers the tools)
from app.capabilities import CHAT_PROVIDERS, FREE_TO_START, HOW_TO_GET
from app.mcp.tools import capability_tools


def _status() -> dict:
    return json.loads(asyncio.run(capability_tools.capability_status()))


def test_every_provider_we_would_ask_for_says_where_to_get_it():
    missing = [p for p in CHAT_PROVIDERS if not HOW_TO_GET.get(p)]
    assert missing == [], f"a picker entry with no instructions behind it: {missing}"


def test_the_instructions_are_a_place_not_an_adjective():
    for provider, sentence in HOW_TO_GET.items():
        if provider in {"mlx"}:
            continue  # bundled with the OS; there is no console to visit
        assert "." in sentence and any(
            token in sentence for token in (".com", ".ai", ".dev")
        ), f"{provider}: {sentence!r} does not say where to go"


def test_the_readout_carries_the_map(monkeypatch):
    monkeypatch.setattr(capability_tools, "_configured_providers", lambda: {"groq"})
    monkeypatch.setattr(capability_tools, "_resolved_embedding_backend", lambda: "ollama")

    out = _status()
    how = out.get("how_to_get")
    assert isinstance(how, dict) and how, "the editor has nothing to read"
    for provider in CHAT_PROVIDERS:
        assert provider in how, f"{provider} missing from the shipped map"
        entry = how[provider]
        assert entry["how"] == HOW_TO_GET[provider]
        assert entry["free"] is (provider in FREE_TO_START)


def test_a_runtime_with_no_key_says_so(monkeypatch):
    """Seen live 2026-08-02: `ollama` and `mlx` led a picker headed "which
    provider is this key for?", and choosing one asked for a key that does not
    exist. They are configured by URL on the server; there is nothing to paste.
    """
    monkeypatch.setattr(capability_tools, "_configured_providers", lambda: {"groq"})
    monkeypatch.setattr(capability_tools, "_resolved_embedding_backend", lambda: "ollama")

    how = _status()["how_to_get"]
    assert how["ollama"]["takes_key"] is False
    assert how["mlx"]["takes_key"] is False
    assert how["groq"]["takes_key"] is True
    assert how["anthropic"]["takes_key"] is True


def test_the_keyless_set_is_read_from_the_cascade_not_relisted(monkeypatch):
    """A second list is a second thing to forget when a runtime is added."""
    from app.providers import cascade

    monkeypatch.setattr(
        cascade, "LOCAL_URL_ATTR", {"ollama": "ollama_url", "vllm": "vllm_url"}
    )
    assert capability_tools._local_providers() == {"ollama", "vllm"}


def test_an_unreadable_cascade_assumes_a_key_is_needed(monkeypatch):
    """Offering a key box for something that does not need one is a smaller
    failure than hiding a provider that does."""
    import builtins

    real = builtins.__import__

    def _boom(name, *a, **k):
        if name == "app.providers.cascade":
            raise RuntimeError("no")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _boom)
    assert capability_tools._local_providers() == set()


def test_a_provider_already_configured_is_marked_as_held(monkeypatch):
    """Telling somebody to go and get what they already have is worse advice
    than saying nothing — the same rule the quota work landed on (08-02)."""
    monkeypatch.setattr(capability_tools, "_configured_providers", lambda: {"groq"})
    monkeypatch.setattr(capability_tools, "_resolved_embedding_backend", lambda: "ollama")

    how = _status()["how_to_get"]
    assert how["groq"]["configured"] is True
    assert how["cerebras"]["configured"] is False
