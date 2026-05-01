"""CloudFlare Workers AI — kendi formatında chat."""

from __future__ import annotations

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
        if not settings.cf_account_id or not settings.cf_api_token:
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
            "Authorization": f"Bearer {settings.cf_api_token}",
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
        return ProviderResponse(
            text=text,
            model=model,
            provider=self.name,
            elapsed_ms=elapsed_ms,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
        )
