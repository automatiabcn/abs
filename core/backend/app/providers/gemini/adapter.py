# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Google Gemini provider — generateContent REST endpoint."""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.config import settings

from ..base import BaseProvider
from ..schemas import ProviderError, ProviderResponse


class GeminiProvider(BaseProvider):
    name = "gemini"
    default_model = "gemini-2.5-flash"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        if not settings.gemini_api_key:
            raise ProviderError(
                "Gemini API key tanımlı değil", provider=self.name, transient=False
            )
        model = model or self.default_model
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={settings.gemini_api_key}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.3),
                "maxOutputTokens": kwargs.get("max_tokens", 1024),
            },
        }

        timeout = kwargs.get("timeout", 60.0)
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Gemini timeout ({timeout}s)", provider=self.name, transient=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Gemini connection error: {exc}", provider=self.name, transient=True
            ) from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        if r.status_code == 429:
            raise ProviderError(
                "Gemini rate limit", provider=self.name, transient=True
            )
        if r.status_code >= 500:
            raise ProviderError(
                f"Gemini 5xx: {r.status_code}", provider=self.name, transient=True
            )
        if r.status_code >= 400:
            raise ProviderError(
                f"Gemini {r.status_code}: {r.text[:200]}",
                provider=self.name,
                transient=False,
            )

        data = r.json()
        try:
            candidates = data["candidates"]
            parts = candidates[0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"Gemini beklenmeyen yanıt: {str(data)[:200]}",
                provider=self.name,
                transient=False,
            ) from exc

        usage = data.get("usageMetadata") or {}
        return ProviderResponse(
            text=text,
            model=model,
            provider=self.name,
            elapsed_ms=elapsed_ms,
            tokens_in=usage.get("promptTokenCount"),
            tokens_out=usage.get("candidatesTokenCount"),
        )
