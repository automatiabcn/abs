"""Round-4 BUG-9 regression — `chat._run_cascade` live wiring.

Founder Phase B evidence (3-turn chat → 3 stub responses):
    "Cascade canli uclari henuz aktif degil."

Round 2 wired `/v1/cascade/run` to `call_with_cascade` but the parallel
helper `app.api.chat._run_cascade()` (used by the SSE chat path) stayed
stubbed. These tests guard that the helper now delegates to the
orchestrator and that the stub message no longer surfaces when at least
one provider is configured.
"""

from __future__ import annotations

import json

import pytest

from app.providers.schemas import ProviderResponse


@pytest.fixture()
def auth_client(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


def _parse_sse(body: bytes) -> list[dict]:
    events: list[dict] = []
    for line in body.decode("utf-8").splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        if payload == "[DONE]":
            events.append({"type": "_done"})
            continue
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return events


def test_run_cascade_calls_orchestrator(monkeypatch):
    """Direct unit-level check: `_run_cascade` invokes call_with_cascade
    and returns the orchestrator's response (no `live_cascade_pending`
    HTTPException)."""
    from app.api import chat as chat_module

    # Disable mock provider so we hit the live branch.
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "off")
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_mock_mode", "off", raising=False)

    monkeypatch.setattr(
        chat_module, "get_active_providers", lambda **_: ["groq", "gemini"]
    )

    seen: dict = {}

    async def _fake_call(prompt: str, **kwargs):
        seen["prompt"] = prompt
        seen["primary"] = kwargs.get("primary")
        seen["fallbacks"] = kwargs.get("fallbacks")
        return ProviderResponse(
            text="Türkiye'nin başkenti Ankara.",
            provider="groq",
            model="llama-3.3-70b",
            elapsed_ms=120,
            tokens_in=10,
            tokens_out=8,
            cached=False,
        )

    monkeypatch.setattr(chat_module, "call_with_cascade", _fake_call)

    import asyncio

    resp = asyncio.run(chat_module._run_cascade("Türkiye başkenti?"))

    assert seen["prompt"] == "Türkiye başkenti?"
    assert seen["primary"] == "groq"
    assert seen["fallbacks"] == ("gemini",)
    assert resp.completion.startswith("Türkiye'nin başkenti")
    assert resp.provider == "groq"
    assert resp.model == "llama-3.3-70b"
    assert resp.tokens_used == 18
    assert resp.mock is False


def test_chat_completions_no_stub_when_providers_configured(
    auth_client, monkeypatch
):
    """End-to-end SSE: with a provider configured, the assistant text
    must NOT contain the Round-3 stub literal."""
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "off")
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_mock_mode", "off", raising=False)

    from app.api import chat as chat_module

    monkeypatch.setattr(
        chat_module, "get_active_providers", lambda **_: ["groq"]
    )

    async def _fake_call(prompt: str, **kwargs):
        return ProviderResponse(
            text="Selam, ben canlı LLM yanıtıyım.",
            provider="groq",
            model="llama-3.3-70b",
            elapsed_ms=80,
            tokens_in=5,
            tokens_out=12,
            cached=False,
        )

    monkeypatch.setattr(chat_module, "call_with_cascade", _fake_call)

    r = auth_client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Selam"}],
            "stream": True,
        },
    )
    assert r.status_code == 200
    body = r.content.decode("utf-8")

    # Round-3 stub literal must not surface.
    assert "Cascade canli uclari henuz aktif degil" not in body
    assert "live_cascade_pending" not in body

    events = _parse_sse(r.content)
    text_chunks = [e for e in events if e.get("type") == "text"]
    assert text_chunks, "expected at least one text chunk"
    joined = "".join(e["content"] for e in text_chunks)
    assert "canlı LLM" in joined or "Selam" in joined

    meta = next((e for e in events if e.get("type") == "meta"), None)
    assert meta is not None
    assert meta["provider"] == "groq"
    assert meta["mock"] is False


def test_chat_completions_no_provider_returns_503(
    auth_client, monkeypatch
):
    """Sprint 2N FAZ E (P1 #2M-018) — no provider → structured HTTP 503.

    Pre-fix: chat completions opened a 200 SSE stream and yielded a
    Türkçe error event, so JS `response.ok = true` lost retry semantics.
    Post-fix: pre-flight provider probe raises HTTPException(503) BEFORE
    StreamingResponse starts. Body is JSON with `error`, `retry_after`,
    `hint`; Retry-After header is set.
    """
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "off")
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_mock_mode", "off", raising=False)

    from app.api import chat as chat_module

    monkeypatch.setattr(chat_module, "get_active_providers", lambda **_: [])

    r = auth_client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Selam"}],
            "stream": True,
        },
    )
    assert r.status_code == 503
    payload = r.json()
    detail = payload.get("detail", payload)
    assert detail["error"] == "all_providers_unavailable"
    assert detail["retry_after"] == 60
    # The hint has to name where to go, not merely that something is wrong.
    assert "Settings" in detail["hint"] and "Providers" in detail["hint"]
    # Retry-After HTTP header set.
    assert r.headers.get("retry-after") == "60"
