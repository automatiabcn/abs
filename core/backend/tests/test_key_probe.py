# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The key probe — a provider's own verdict on a key, before it is stored.

The probe's one job is to tell three things apart: the provider said yes, the
provider said no, and nobody answered. Conflating the last two is how a
network blip would eat a perfectly good key.
"""

from __future__ import annotations

import httpx

from app.providers import key_probe


class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_a_200_is_valid(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(200))
    assert key_probe.probe_provider_key("groq", "gsk-x").status == "valid"


def test_a_401_is_the_providers_no(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(401))
    out = key_probe.probe_provider_key("cohere", "sk-mangled")
    assert out.status == "rejected"
    assert "cohere" in out.detail


def test_geminis_400_for_a_malformed_key_is_a_no(monkeypatch):
    # Live: a key one character short of AIza… gets 400 INVALID_ARGUMENT.
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(400))
    assert key_probe.probe_provider_key("gemini", "AIza-short").status == "rejected"


def test_a_network_fault_is_not_a_verdict(monkeypatch):
    def _boom(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx, "get", _boom)
    out = key_probe.probe_provider_key("cerebras", "csk-x")
    assert out.status == "unreachable"
    assert "csk-x" not in out.detail, "the key must never appear in a message"


def test_a_5xx_does_not_condemn_the_key(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(503))
    assert key_probe.probe_provider_key("openrouter", "or-x").status == "unreachable"


def test_an_unknown_provider_is_unvalidated_not_guessed(monkeypatch):
    called = []
    monkeypatch.setattr(httpx, "get", lambda *a, **k: called.append(1))
    out = key_probe.probe_provider_key("ollama", "anything")
    assert out.status == "unvalidated"
    assert called == [], "no probe known means no call made"
