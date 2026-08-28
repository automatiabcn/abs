# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Groq Cloud provider — OpenAI uyumlu chat completions."""

from __future__ import annotations

import re
from typing import Any, AsyncIterator, Dict, Optional

from app.config import settings

from ..base import (
    BaseProvider,
    StreamEvent,
    openai_compatible_chat,
    openai_compatible_stream,
)
from ..schemas import ProviderResponse

# Groq retired its Llama 3.x and Qwen3-32B lines on 2026-08-16 (live catalogue
# that day: gpt-oss-120b / gpt-oss-20b / qwen3.6-27b / compound / whisper /
# guards). The old default `llama-3.1-8b-instant` answered `model_not_found`
# for two days while every panel still said "groq ready" — an audit, not a
# customer, found it. The default is the fast free model that exists today;
# `app/providers/catalog_watch.py` checks every pinned model against the live
# catalogue so the next retirement is announced instead of discovered.
DEFAULT_MODEL = "openai/gpt-oss-20b"

# Models that emit chain-of-thought unless told not to. Qwen 3.6 writes a
# `<think>` block first and, under a small token budget, never gets past it
# (measured: 80 tokens = 80 tokens of thinking, empty answer). Unless the
# caller asks for reasoning explicitly, these run with reasoning off.
_THINKING_MODELS = ("qwen/qwen3.6",)
_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class GroqProvider(BaseProvider):
    name = "groq"
    default_model = DEFAULT_MODEL

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        chosen = model or self.default_model
        extra: Dict[str, Any] = {}
        effort = kwargs.get("reasoning_effort")
        if effort is None and chosen.startswith(_THINKING_MODELS):
            effort = "none"
        if effort:
            extra["reasoning_effort"] = effort
        resp = await openai_compatible_chat(
            url="https://api.groq.com/openai/v1/chat/completions",
            api_key=kwargs.get("api_key") or settings.groq_api_key,
            model=chosen,
            prompt=prompt,
            provider_name=self.name,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.3),
            timeout=kwargs.get("timeout", 30.0),
            response_format=kwargs.get("response_format"),
            extra_body=extra or None,
        )
        # A stray think block that still made it through (reasoning requested,
        # or a model we do not know thinks) is not part of the answer.
        text = getattr(resp, "text", None)
        if text and "<think>" in text:
            cleaned = _THINK_BLOCK.sub("", text).lstrip("\n")
            try:
                resp.text = cleaned  # type: ignore[misc]
            except Exception:  # noqa: BLE001 — frozen model: return as-is
                pass
        return resp

    streams = True

    async def stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        chosen = model or self.default_model
        extra: Dict[str, Any] = {}
        effort = kwargs.get("reasoning_effort")
        if effort is None and chosen.startswith(_THINKING_MODELS):
            effort = "none"
        if effort:
            extra["reasoning_effort"] = effort
        async for ev in openai_compatible_stream(
            url="https://api.groq.com/openai/v1/chat/completions",
            api_key=kwargs.get("api_key") or settings.groq_api_key,
            model=chosen,
            prompt=prompt,
            provider_name=self.name,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.3),
            timeout=kwargs.get("timeout", 30.0),
            extra_body=extra or None,
        ):
            yield ev
