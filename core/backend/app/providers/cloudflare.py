# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""CloudFlare Workers AI — kendi formatında chat."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx

from app.config import settings

from .base import BaseProvider
from .schemas import ProviderError, ProviderResponse


class CloudflareProvider(BaseProvider):
    name = "cloudflare"
    default_model = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        _token = kwargs.get("api_key") or settings.cf_api_token
        if not settings.cf_account_id or not _token:
            raise ProviderError(
                "CloudFlare account_id veya api_token tanımlı değil",
                provider=self.name,
                transient=False,
            )

        model = model or self.default_model
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{settings.cf_account_id}/ai/run/{model}"
        )
        headers = {
            "Authorization": f"Bearer {_token}",
            "Content-Type": "application/json",
        }
        body = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", 1024),
            "temperature": kwargs.get("temperature", 0.3),
        }

        timeout = kwargs.get("timeout", 30.0)
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"CloudFlare timeout ({timeout}s)", provider=self.name, transient=True
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"CloudFlare connection error: {exc}", provider=self.name, transient=True
            ) from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        if r.status_code == 429:
            raise ProviderError(
                "CloudFlare rate limit", provider=self.name, transient=True
            )
        if r.status_code >= 500:
            raise ProviderError(
                f"CloudFlare 5xx: {r.status_code}", provider=self.name, transient=True
            )
        if r.status_code >= 400:
            raise ProviderError(
                f"CloudFlare {r.status_code}: {r.text[:200]}",
                provider=self.name,
                transient=False,
            )

        data = r.json()
        if not data.get("success", False):
            errs = data.get("errors") or []
            msg = errs[0].get("message") if errs else "unknown error"
            raise ProviderError(
                f"CloudFlare API: {msg}", provider=self.name, transient=False
            )

        result = data.get("result") or {}
        text = result.get("response") or ""
        usage = result.get("usage") or {}
        # Sprint 2N.4 — Cloudflare Workers AI sometimes returns a dict
        # (e.g. structured JSON output for workflow synth). ProviderResponse
        # expects str → coerce non-string to JSON to avoid ValidationError.
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)
        return ProviderResponse(
            text=text,
            model=model,
            provider=self.name,
            elapsed_ms=elapsed_ms,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
        )
