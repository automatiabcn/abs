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
from ._auth import gemini_headers


# What thinking costs here: the model's own reasoning is written INTO the
# maxOutputTokens budget. gemini-2.5-flash asked for 200 tokens answered with 7
# ("The `vip_total` function") and finishReason MAX_TOKENS; asked for 20 it
# answered with nothing, the cascade called that a failure and moved on, and
# a request of the day's free quota was spent on silence (audit 2026-08-18).
# So unless a caller asks for reasoning, thinking is turned down where the
# API allows it — and the knob differs by family (measured 2026-08-16):
#   2.5 flash / flash-lite      thinkingBudget: 0 (off)
#   2.5 pro                     cannot be turned off; nothing is sent
#   3.7                         thinkingBudget: 0
#   other 3.x                   thinkingLevel: "low" (budget is rejected;
#                               "minimal" is not accepted everywhere)
def thinking_config(model: str, reasoning_effort: Optional[str] = None) -> Optional[dict]:
    m = (model or "").lower()
    if reasoning_effort in ("default", "high", "medium"):
        return None  # the caller wants the model to think; leave the API default
    if m.startswith("gemini-2.5-pro"):
        return None
    if m.startswith("gemini-2.5-"):
        return {"thinkingBudget": 0}
    if m.startswith("gemini-3.7"):
        return {"thinkingBudget": 0}
    if m.startswith("gemini-3."):
        return {"thinkingLevel": "low"}
    return None


class GeminiProvider(BaseProvider):
    name = "gemini"
    default_model = "gemini-2.5-flash"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        _key = kwargs.get("api_key") or settings.gemini_api_key
        if not _key:
            raise ProviderError(
                "Gemini API key is not configured", provider=self.name, transient=False
            )
        model = model or self.default_model
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        gen_cfg: dict = {
            "temperature": kwargs.get("temperature", 0.3),
            "maxOutputTokens": kwargs.get("max_tokens", 1024),
        }
        thinking = thinking_config(model, kwargs.get("reasoning_effort"))
        if thinking:
            gen_cfg["thinkingConfig"] = thinking
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_cfg,
        }

        timeout = kwargs.get("timeout", 60.0)
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    url,
                    headers=gemini_headers(_key),
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
            raise ProviderError("Gemini rate limit", provider=self.name, transient=True)
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

        try:
            data = r.json()
        except ValueError as exc:
            # A 2xx with a malformed body must fail over to the next provider,
            # not crash the whole cascade with an uncaught JSONDecodeError.
            raise ProviderError(
                "Gemini JSON parse error", provider=self.name, transient=True
            ) from exc
        try:
            candidates = data["candidates"]
            parts = candidates[0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"Gemini unexpected response: {str(data)[:200]}",
                provider=self.name,
                transient=False,
            ) from exc

        usage = data.get("usageMetadata") or {}
        # Gemini spells it `finishReason: "MAX_TOKENS"` — camel case and
        # shouted, where OpenAI says `finish_reason: "length"`. Read through
        # the same helper so a third spelling only has to be learned once.
        from app.providers.base import was_cut_off

        # Thinking tokens are billed and they come out of maxOutputTokens;
        # counting only the visible answer under-reported both.
        visible = int(usage.get("candidatesTokenCount") or 0)
        thoughts = int(usage.get("thoughtsTokenCount") or 0)
        return ProviderResponse(
            text=text,
            model=model,
            provider=self.name,
            elapsed_ms=elapsed_ms,
            tokens_in=usage.get("promptTokenCount"),
            tokens_out=(visible + thoughts) if usage else None,
            truncated=was_cut_off(candidates[0].get("finishReason")),
        )
