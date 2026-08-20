"""Gemini's reasoning is written into maxOutputTokens. Unless a caller asks for
it, thinking is turned down where the API allows — measured 2026-08-18:
gemini-2.5-flash with 200 tokens answered 7 ("The `vip_total` function")
and MAX_TOKENS; with 20 it answered nothing and the cascade moved on, one
free-quota request spent on silence.
"""

from __future__ import annotations

import httpx
import pytest

from app.providers.gemini import adapter as ga


@pytest.mark.parametrize(
    "model,expect",
    [
        ("gemini-2.5-flash", {"thinkingBudget": 0}),
        ("gemini-2.5-flash-lite", {"thinkingBudget": 0}),
        ("gemini-2.5-pro", None),  # cannot be turned off; do not send a knob it rejects
        ("gemini-3.7-flash", {"thinkingBudget": 0}),
        ("gemini-3.6-flash", {"thinkingLevel": "low"}),
        ("gemini-3.5-flash-lite", {"thinkingLevel": "low"}),
        ("gemini-flash-latest", None),  # unknown family: leave the API default
    ],
)
def test_the_knob_matches_the_family(model, expect):
    assert ga.thinking_config(model) == expect


def test_a_caller_that_wants_reasoning_gets_the_default():
    assert ga.thinking_config("gemini-2.5-flash", "high") is None


@pytest.mark.asyncio
async def test_the_request_carries_the_config_and_the_answer_counts_thoughts(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen["body"] = _json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "hi"}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2, "thoughtsTokenCount": 30},
            },
        )

    real = httpx.AsyncClient

    def fake_client(*a, **k):
        k["transport"] = httpx.MockTransport(handler)
        return real(*a, **k)

    monkeypatch.setattr(ga.httpx, "AsyncClient", fake_client)
    r = await ga.GeminiProvider().call("x", model="gemini-2.5-flash", api_key="k", max_tokens=200)
    assert seen["body"]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert seen["body"]["generationConfig"]["maxOutputTokens"] == 200
    assert r.tokens_out == 32  # visible + thoughts: both billed, both in the budget
    assert r.truncated is False
