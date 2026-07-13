"""T-R03 fix #4 — Ollama-first cascade tests.

Validates the priority chain `ollama → groq → anthropic`:

1. Ollama up + healthy → Ollama response, no fallback fired.
2. Ollama down (httpx ConnectError) → falls back to Groq.
3. Ollama hangs past `ollama_first_health_timeout_s` → falls back to Groq.
4. Feature flag off → raises RuntimeError (caller picks a different chain).

We mock the cascade orchestrator's provider dispatch so the test stays fast
(no real httpx round-trip).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.cascade import ollama_first as of
from app.providers.schemas import ProviderError, ProviderResponse


def _ok(provider: str, text: str) -> ProviderResponse:
    return ProviderResponse(
        text=text,
        model="mock",
        provider=provider,
        elapsed_ms=42,
        tokens_in=10,
        tokens_out=20,
    )


@pytest.fixture
def enable_ollama_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.cascade.ollama_first.settings.ollama_first_enabled", True)


@pytest.mark.asyncio
async def test_ollama_first_uses_ollama_when_healthy(
    enable_ollama_first: None,
) -> None:
    async def fake_call(prompt: str, **kwargs: Any) -> ProviderResponse:
        assert kwargs["primary"] == "ollama"
        return _ok("ollama", "yerel cevap")

    with patch.object(
        of, "call_with_cascade", new=AsyncMock(side_effect=fake_call)
    ) as mock:
        resp = await of.call_ollama_first("merhaba")
    assert resp.provider == "ollama"
    assert resp.text == "yerel cevap"
    # Only the ollama call fired — no fallback.
    assert mock.call_count == 1


@pytest.mark.asyncio
async def test_ollama_first_falls_back_to_groq_on_connect_error(
    enable_ollama_first: None,
) -> None:
    calls: list[str] = []

    async def fake_call(prompt: str, **kwargs: Any) -> ProviderResponse:
        primary = kwargs["primary"]
        calls.append(primary)
        if primary == "ollama":
            raise ProviderError(
                "Ollama connection error: ConnectError",
                provider="ollama",
                transient=True,
            )
        return _ok(primary, "groq cevabı")

    with patch.object(of, "call_with_cascade", new=AsyncMock(side_effect=fake_call)):
        resp = await of.call_ollama_first("merhaba")
    assert resp.provider == "groq"
    assert calls == ["ollama", "groq"]


@pytest.mark.asyncio
async def test_ollama_first_health_timeout_triggers_groq(
    enable_ollama_first: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.cascade.ollama_first.settings.ollama_first_health_timeout_s", 0.05
    )

    async def fake_call(prompt: str, **kwargs: Any) -> ProviderResponse:
        if kwargs["primary"] == "ollama":
            await asyncio.sleep(0.5)  # past the 50 ms timeout
            return _ok("ollama", "should never reach")
        return _ok(kwargs["primary"], "groq")

    with patch.object(of, "call_with_cascade", new=AsyncMock(side_effect=fake_call)):
        resp = await of.call_ollama_first("merhaba")
    assert resp.provider == "groq"


@pytest.mark.asyncio
async def test_ollama_first_falls_through_to_anthropic_when_groq_down(
    enable_ollama_first: None,
) -> None:
    calls: list[str] = []

    async def fake_call(prompt: str, **kwargs: Any) -> ProviderResponse:
        name = kwargs["primary"]
        calls.append(name)
        if name in {"ollama", "groq"}:
            raise ProviderError(f"{name} down", provider=name, transient=True)
        return _ok("anthropic", "anthropic cevap")

    with patch.object(of, "call_with_cascade", new=AsyncMock(side_effect=fake_call)):
        resp = await of.call_ollama_first("merhaba")
    assert resp.provider == "anthropic"
    assert calls == ["ollama", "groq", "anthropic"]


@pytest.mark.asyncio
async def test_ollama_first_disabled_raises() -> None:
    with pytest.raises(RuntimeError, match="ollama_first_enabled=false"):
        await of.call_ollama_first("merhaba")


@pytest.mark.asyncio
async def test_non_transient_error_propagates(enable_ollama_first: None) -> None:
    async def fake_call(prompt: str, **kwargs: Any) -> ProviderResponse:
        raise ProviderError("config bozuk", provider=kwargs["primary"], transient=False)

    with patch.object(of, "call_with_cascade", new=AsyncMock(side_effect=fake_call)):
        with pytest.raises(ProviderError) as excinfo:
            await of.call_ollama_first("merhaba")
    assert excinfo.value.transient is False
