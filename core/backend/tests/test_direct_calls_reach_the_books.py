"""Calls that bypass the cascade — the judge, the second opinion — reach the
same usage log, quota meter and health readout as the cascade's; Cohere's
answers carry their token counts.

Audit 2026-08-18: cohere answered with tokens None → cost 0 / free False;
judge and disagree called adapters directly and were invisible to every
ledger — a paid second-opinion leg never reached the cost page.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.cascade import orchestrator as orch
from app.providers.schemas import ProviderError, ProviderResponse


def test_cohere_reads_billed_units():
    from app.providers.cohere.adapter import _cohere_usage

    resp = SimpleNamespace(usage=SimpleNamespace(
        billed_units=SimpleNamespace(input_tokens=12, output_tokens=7),
        tokens=SimpleNamespace(input_tokens=15, output_tokens=8),
    ))
    assert _cohere_usage(resp) == (12, 7)
    bare = SimpleNamespace(usage=None)
    assert _cohere_usage(bare) == (None, None)


def test_record_direct_call_books_success_and_failure(monkeypatch):
    seen = {"meter": [], "quota": [], "health": []}
    monkeypatch.setattr(orch, "_meter", lambda resp, *, provider, tenant_id: seen["meter"].append((provider, tenant_id)))
    monkeypatch.setattr(orch, "_record_quota", lambda provider, **k: seen["quota"].append((provider, k.get("status_code"), k.get("tokens"))))
    monkeypatch.setattr(orch._health, "note_success", lambda p, **k: seen["health"].append(("ok", p)))
    monkeypatch.setattr(orch._health, "note_failure", lambda p, **k: seen["health"].append(("fail", p, k.get("permanent"))))
    orch.record_direct_call(ProviderResponse(text="x", provider="groq", model="m", tokens_in=3, tokens_out=4), provider="groq", tenant_id="t", model="m")
    orch.record_direct_call(None, provider="cerebras", tenant_id="t", model="m", exc=ProviderError("402 payment", provider="cerebras", transient=False))
    assert seen["meter"] == [("groq", "t")]
    assert ("groq", 200, 7) in seen["quota"]
    assert ("cerebras", 500, None) in seen["quota"] or any(q[0] == "cerebras" and q[1] == 500 for q in seen["quota"])
    assert ("ok", "groq") in seen["health"]
    assert ("fail", "cerebras", True) in seen["health"]


def test_the_judge_books_its_call(monkeypatch):
    from app.judge import senior

    booked = []
    monkeypatch.setattr(senior, "_book", lambda resp, **k: booked.append((k["provider"], resp is not None)))
    monkeypatch.setattr(senior, "owner_key_for", lambda *a, **k: "key")

    class P:
        async def call(self, prompt, **kw):
            return ProviderResponse(text='{"score": 8, "teaching": "fine"}', provider="groq", model="m")

    monkeypatch.setattr(senior, "get_provider", lambda n: P())
    out = asyncio.run(senior._llm_judge("x = 1", diff_text="+x = 1", file_path="a.py", tenant_id="t"))
    assert out["score"] == 8
    assert booked and booked[0] == ("groq", True)


def test_the_second_opinion_books_each_leg(monkeypatch):
    from app.disagreement import detector

    booked = []
    monkeypatch.setattr("app.cascade.orchestrator.record_direct_call", lambda resp, **k: booked.append((k["provider"], resp is not None)))
    monkeypatch.setattr(detector, "byok_providers", lambda t, u: frozenset())
    monkeypatch.setattr(detector, "get_active_providers", lambda **k: ["groq", "cohere"])
    monkeypatch.setattr("app.providers.paid_access.restrict_chain", lambda chain, *a, **k: list(chain))
    monkeypatch.setattr(detector, "owner_key_for", lambda *a, **k: None)

    class P:
        def __init__(self, n):
            self.n = n

        async def call(self, prompt, **kw):
            if self.n == "cohere":
                raise RuntimeError("down")
            return ProviderResponse(text="a", provider="groq", model="m")

    monkeypatch.setattr(detector, "get_provider", lambda n: P(n))
    asyncio.run(detector.ask_disagree("q", tenant_id="t", user_subject="u"))
    assert ("groq", True) in booked and ("cohere", False) in booked
