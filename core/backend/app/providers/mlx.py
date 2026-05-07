# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""MLX provider — Apple Silicon Neural Engine HTTP bridge (010).

SERVER quick.py::ask_mlx pattern. Bridge daemon ABS dışında çalışır
(M4'te `mlx_lm.server` veya custom MLX server, default port 11436).
ABS_MLX_URL boş ise non-transient ProviderError.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.config import settings

from .base import BaseProvider
from .schemas import ProviderError, ProviderResponse


class MLXProvider(BaseProvider):
    name = "mlx"
    default_model = "llama3-8b"
    default_timeout = 30.0

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        if not settings.mlx_url:
            raise ProviderError(
                "MLX_URL tanımlı değil — Apple Silicon Neural Engine bridge yok",
                provider=self.name,
                transient=False,
            )
        model = model or self.default_model
        url = settings.mlx_url.rstrip("/") + "/v1/generate"
        body = {
            "model": model,
            "prompt": prompt,
            "max_tokens": kwargs.get("max_tokens", 1024),
        }
        timeout = kwargs.get("timeout", self.default_timeout)
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"MLX timeout ({timeout}s)", provider=self.name, transient=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"MLX bağlantı: {exc}", provider=self.name, transient=True
            ) from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)
        if r.status_code >= 400:
            raise ProviderError(
                f"MLX {r.status_code}: {r.text[:200]}",
                provider=self.name,
                transient=(r.status_code >= 500),
            )
        try:
            data = r.json()
        except ValueError as exc:
            raise ProviderError(
                "MLX JSON parse", provider=self.name, transient=True
            ) from exc

        text = data.get("response") or ""
        if not text and "error" in data:
            raise ProviderError(
                f"MLX: {data['error']}", provider=self.name, transient=True
            )

        return ProviderResponse(
            text=text,
            model=model,
            provider=self.name,
            elapsed_ms=elapsed_ms,
            tokens_in=data.get("prompt_tokens"),
            tokens_out=data.get("completion_tokens"),
        )
