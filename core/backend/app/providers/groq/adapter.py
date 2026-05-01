"""Groq Cloud provider — OpenAI uyumlu chat completions."""

from __future__ import annotations

from typing import Any, Optional

from app.config import settings

from ..base import BaseProvider, openai_compatible_chat
from ..schemas import ProviderResponse


class GroqProvider(BaseProvider):
    name = "groq"
    default_model = "llama-3.1-8b-instant"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        return await openai_compatible_chat(
            url="https://api.groq.com/openai/v1/chat/completions",
            api_key=settings.groq_api_key,
            model=model or self.default_model,
            prompt=prompt,
            provider_name=self.name,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.3),
            timeout=kwargs.get("timeout", 30.0),
        )
