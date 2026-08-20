"""What the Groq adapter and its callers do after the 2026-08-16 retirement.

Three things a silent edit must argue with:
1. qwen3.6 runs with reasoning OFF unless asked (with 80 tokens it otherwise
   answers with 80 tokens of <think> and no code — measured live).
2. A stray <think> block never reaches the caller.
3. `ask_groq_fast`'s fallback gets its OWN model — the primary's id handed to
   cerebras is how a groq retirement read as "cerebras 404".
"""

from __future__ import annotations

import httpx
import pytest

from app.providers.groq.adapter import DEFAULT_MODEL, GroqProvider


def _capture(monkeypatch, content="ok"):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen["body"] = _json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    from app.providers import base as _base

    real = httpx.AsyncClient

    def fake_client(*a, **k):
        k["transport"] = httpx.MockTransport(handler)
        return real(*a, **k)

    monkeypatch.setattr(_base.httpx, "AsyncClient", fake_client)
    return seen


@pytest.mark.asyncio
async def test_default_model_exists_in_the_live_catalogue_shape():
    assert DEFAULT_MODEL == "openai/gpt-oss-20b"


@pytest.mark.asyncio
async def test_qwen36_gets_reasoning_off_by_default(monkeypatch):
    seen = _capture(monkeypatch)
    await GroqProvider().call("x", model="qwen/qwen3.6-27b", api_key="k")
    assert seen["body"]["reasoning_effort"] == "none"


@pytest.mark.asyncio
async def test_a_caller_that_wants_reasoning_gets_it(monkeypatch):
    seen = _capture(monkeypatch)
    await GroqProvider().call(
        "x", model="qwen/qwen3.6-27b", api_key="k", reasoning_effort="default"
    )
    assert seen["body"]["reasoning_effort"] == "default"


@pytest.mark.asyncio
async def test_other_models_are_not_touched(monkeypatch):
    seen = _capture(monkeypatch)
    await GroqProvider().call("x", model="openai/gpt-oss-20b", api_key="k")
    assert "reasoning_effort" not in seen["body"]


@pytest.mark.asyncio
async def test_a_stray_think_block_is_stripped(monkeypatch):
    _capture(monkeypatch, content="<think>\nlong thoughts\n</think>\nn % 2 != 0")
    r = await GroqProvider().call("x", model="qwen/qwen3.6-27b", api_key="k")
    assert r.text == "n % 2 != 0"


@pytest.mark.asyncio
async def test_ask_groq_fast_fallback_carries_its_own_model(monkeypatch):
    import app.mcp.server  # noqa: F401 — circular import guard, registers tools
    from app.mcp.tools import basic_providers as bp

    seen = {}

    async def fake_cascade(prompt, **kwargs):
        seen.update(kwargs)

        class R:
            text = "ok"

        return R()

    monkeypatch.setattr(bp, "call_with_cascade", fake_cascade)
    await bp.ask_groq_fast("hi")
    assert seen["primary"] == "groq"
    assert seen["models"]["groq"] == "openai/gpt-oss-20b"
    # The fallback is not handed groq's model.
    assert seen["models"]["cerebras"] != seen["models"]["groq"]
    assert "model" not in seen  # one shared model would reach every leg


@pytest.mark.asyncio
async def test_fim_asks_groq_with_reasoning_off(monkeypatch):
    from app.fim import complete as fim

    seen = {}

    class P:
        async def call(self, prompt, **kwargs):
            seen.update(kwargs)

            class R:
                text = "n % 2 != 0"
                model = kwargs.get("model", "")

            return R()

    monkeypatch.setattr(fim, "_free_fast_chain", lambda *a, **k: ["groq"])
    monkeypatch.setattr("app.providers.registry.get_provider", lambda name: P())
    out = await fim.complete(
        prefix="def is_odd(n):\n    return ", suffix="\n", language="python"
    )
    assert out["ok"] is True
    assert seen["model"] == "qwen/qwen3.6-27b"
    assert seen["reasoning_effort"] == "none"
