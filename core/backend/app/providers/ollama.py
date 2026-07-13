# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Ollama provider — local models over /api/chat."""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.config import settings

from .base import BaseProvider
from .schemas import ProviderError, ProviderResponse


class OllamaProvider(BaseProvider):
    name = "ollama"
    default_model = "phi4"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        if not settings.ollama_url:
            raise ProviderError(
                "OLLAMA_URL is not configured — no local Ollama",
                provider=self.name,
                transient=False,
            )
        model = model or self.default_model
        url = settings.ollama_url.rstrip("/") + "/api/chat"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.3),
                "num_predict": kwargs.get("max_tokens", 1024),
            },
        }

        timeout = kwargs.get("timeout", 120.0)
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Ollama timeout ({timeout}s)", provider=self.name, transient=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Ollama connection error: {exc}", provider=self.name, transient=True
            ) from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)
        if r.status_code >= 400:
            raise ProviderError(
                f"Ollama {r.status_code}: {r.text[:200]}",
                provider=self.name,
                transient=(r.status_code >= 500),
            )

        try:
            data = r.json()
        except ValueError as exc:
            # A 2xx with a malformed/empty body is transient infra noise — a
            # ValueError here is neither a ProviderError nor a recognised
            # transient infra exception, so it would crash the cascade with a
            # 500 instead of failing over to the next provider.
            raise ProviderError(
                "Ollama JSON parse error", provider=self.name, transient=True
            ) from exc
        msg = data.get("message") or {}
        text = msg.get("content", "")
        return ProviderResponse(
            text=text,
            model=model,
            provider=self.name,
            elapsed_ms=elapsed_ms,
            tokens_in=data.get("prompt_eval_count"),
            tokens_out=data.get("eval_count"),
        )
