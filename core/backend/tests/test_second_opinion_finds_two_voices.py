"""A second opinion needs two voices. Known-dead providers are asked last, and
the run keeps asking until two have answered or nobody is left.

Audit 2026-08-18: three preferred providers were asked; two were dead
(payment required; a retired model); gemini and cohere — alive, configured —
were never asked. status: single.
"""

from __future__ import annotations

import asyncio

import pytest

from app.cascade import provider_health as ph
from app.disagreement import detector


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    ph.reset_for_tests()
    monkeypatch.setattr(ph, "_path", lambda: str(tmp_path / "ph.json"))
    monkeypatch.setattr(detector, "byok_providers", lambda t, u: frozenset())
    monkeypatch.setattr(
        detector, "get_active_providers",
        lambda **k: ["groq", "cloudflare", "cerebras", "gemini", "cohere"],
    )
    monkeypatch.setattr("app.providers.paid_access.restrict_chain", lambda chain, *a, **k: list(chain))


def test_known_dead_providers_are_asked_last():
    ph.note_failure("cerebras", tenant="t", permanent=True, detail="402 payment required")
    ph.note_failure("groq", tenant="t", permanent=True, detail="404 model_not_found")
    order = [n for n, _p, _m in detector.choose_models("t", "u", limit=None)]
    assert order[:3] == ["cloudflare", "gemini", "cohere"]
    assert set(order[3:]) == {"cerebras", "groq"}


def test_the_run_keeps_asking_until_two_answer(monkeypatch):
    answers = {"groq": "", "cloudflare": "", "cerebras": "", "gemini": "use ==", "cohere": "== compares values"}
    calls = []

    class P:
        def __init__(self, name):
            self.name = name

        async def call(self, prompt, **kw):
            calls.append(self.name)
            if not answers[self.name]:
                raise RuntimeError("dead")

            class R:
                text = answers[self.name]

            return R()

    monkeypatch.setattr(detector, "get_provider", lambda n: P(n))
    monkeypatch.setattr(detector, "owner_key_for", lambda *a, **k: None)
    out = asyncio.run(detector.ask_disagree("is == right?", tenant_id="t", user_subject="u"))
    assert out["status"] == "ok", out
    assert set(out["models"]) == {"gemini", "cohere"}
    # everybody up to the second voice was asked, and no further
    assert set(calls) == {"groq", "cloudflare", "cerebras", "gemini", "cohere"}


def test_a_reasoning_model_is_given_room(monkeypatch):
    seen = {}

    class P:
        def __init__(self, name):
            self.name = name

        async def call(self, prompt, **kw):
            seen[self.name] = kw.get("max_tokens")

            class R:
                text = "x"

            return R()

    monkeypatch.setattr(detector, "get_provider", lambda n: P(n))
    monkeypatch.setattr(detector, "owner_key_for", lambda *a, **k: None)
    asyncio.run(detector.ask_disagree("q", tenant_id="t", user_subject="u"))
    assert seen["cloudflare"] == 2048  # kimi-k2.5 thinks first
    assert seen["groq"] == 1024
