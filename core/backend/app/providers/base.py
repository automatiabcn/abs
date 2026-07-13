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
            f"{provider_name} API key is not configured", provider=provider_name, transient=False
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
            f"{provider_name} timeout ({timeout}s)", provider=provider_name, transient=True
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"{provider_name} connection error: {exc}", provider=provider_name, transient=True
        ) from exc

    elapsed_ms = int((time.monotonic() - start) * 1000)

    if r.status_code >= 500:
        raise ProviderError(
            f"{provider_name} 5xx: {r.status_code}", provider=provider_name, transient=True
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

    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(
            f"{provider_name} unexpected response: {str(data)[:200]}",
            provider=provider_name,
            transient=False,
        ) from exc

    usage = data.get("usage") or {}
    return ProviderResponse(
        text=text,
        model=model,
        provider=provider_name,
        elapsed_ms=elapsed_ms,
        tokens_in=usage.get("prompt_tokens"),
        tokens_out=usage.get("completion_tokens"),
    )
