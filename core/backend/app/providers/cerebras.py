# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Cerebras Cloud provider — OpenAI uyumlu."""

from __future__ import annotations

from typing import Any, Optional

from app.config import settings

from .base import BaseProvider, openai_compatible_chat
from .schemas import ProviderResponse


class CerebrasProvider(BaseProvider):
    name = "cerebras"
    default_model = "qwen-3-235b-a22b-instruct-2507"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        return await openai_compatible_chat(
            url="https://api.cerebras.ai/v1/chat/completions",
            api_key=settings.cerebras_api_key,
            model=model or self.default_model,
            prompt=prompt,
            provider_name=self.name,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.3),
            timeout=kwargs.get("timeout", 30.0),
        )
