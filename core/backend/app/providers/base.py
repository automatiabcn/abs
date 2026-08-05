# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Provider base class + the shared OpenAI-compatible chat completions call."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx

from .schemas import ProviderError, ProviderResponse


# The spellings vendors use to say "I ran out of room". OpenAI-compatible APIs
# say `length`; Anthropic says `max_tokens`; Gemini shouts `MAX_TOKENS`. Same
# fact, three dialects — and a guard that knows only one of them is a guard
# switched off for two thirds of the chain.
_CUT_OFF = {"length", "max_tokens", "max_output_tokens"}


def was_cut_off(finish_reason: Any) -> bool:
    """True when a provider says its answer stopped at the token limit.

    Anything else — "stop", an empty string, a missing field, a provider that
    reports nothing at all — is False. Silence is not evidence of truncation,
    and treating it as such would refuse every answer from the quiet providers.
    """
    if not isinstance(finish_reason, str):
        return False
    return finish_reason.strip().lower() in _CUT_OFF


def read_openai_payload(
    data: Dict[str, Any],
    *,
    provider: str,
    model: str,
    elapsed_ms: int,
) -> ProviderResponse:
    """One OpenAI-compatible response body, normalised.

    Split out of the HTTP call so the parsing can be tested against a payload
    rather than a live provider — and so every OpenAI-shaped provider picks up
    `truncated` by construction instead of by being remembered.
    """
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(
            f"{provider} unexpected response: {str(data)[:200]}",
            provider=provider,
            transient=False,
        ) from exc

    usage = data.get("usage") or {}
    return ProviderResponse(
        text=text,
        model=model,
        provider=provider,
        elapsed_ms=elapsed_ms,
        tokens_in=usage.get("prompt_tokens"),
        tokens_out=usage.get("completion_tokens"),
        truncated=was_cut_off(choice.get("finish_reason")),
    )


class BaseProvider(ABC):
    """Abstract base every provider client derives from."""

    name: str = "base"
    default_model: str = ""
    default_timeout: float = 30.0

    @abstractmethod
    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Send the prompt to the model, return a normalized ProviderResponse.

        Failures must be raised as ProviderError with `transient` set correctly:
        the cascade uses that flag to decide whether failing over can help.
        """
        raise NotImplementedError


async def openai_compatible_chat(
    *,
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    provider_name: str,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    timeout: float = 30.0,
    extra_headers: Optional[Dict[str, str]] = None,
    response_format: Optional[dict] = None,
) -> ProviderResponse:
    """Shared call for any OpenAI-compatible /chat/completions endpoint.

    Groq, Cerebras, OpenRouter and vLLM all speak the same schema, so they get
    one implementation and one place where transient-vs-permanent is decided.
    """
    if not api_key:
        raise ProviderError(
            f"{provider_name} API key is not configured",
            provider=provider_name,
            transient=False,
        )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    # Optional structured-output enforcement (OpenAI/Groq json_object mode).
    # Default None → body unchanged, so existing chat/qual callers are unaffected.
    if response_format:
        body["response_format"] = response_format

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise ProviderError(
            f"{provider_name} timeout ({timeout}s)",
            provider=provider_name,
            transient=True,
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"{provider_name} connection error: {exc}",
            provider=provider_name,
            transient=True,
        ) from exc

    elapsed_ms = int((time.monotonic() - start) * 1000)

    if r.status_code >= 500:
        raise ProviderError(
            f"{provider_name} 5xx: {r.status_code}",
            provider=provider_name,
            transient=True,
        )
    if r.status_code == 429:
        raise ProviderError(
            f"{provider_name} rate limit", provider=provider_name, transient=True
        )
    if r.status_code >= 400:
        raise ProviderError(
            f"{provider_name} {r.status_code}: {r.text[:200]}",
            provider=provider_name,
            transient=False,
        )

    try:
        data = r.json()
    except ValueError as exc:
        raise ProviderError(
            f"{provider_name} JSON parse error", provider=provider_name, transient=True
        ) from exc

    return read_openai_payload(
        data, provider=provider_name, model=model, elapsed_ms=elapsed_ms
    )
