"""OpenRouter provider — OpenAI uyumlu passthrough.

Free models pool: DeepSeek R1, Qwen3 Coder, Gemma 3 family, MiniMax M2.
Rate limit pool ile ücretsiz modeller ağır — fallback'i tek çağrıda zorlamayın.
"""

from __future__ import annotations

from typing import Any, Optional

from app.config import settings

from ..base import BaseProvider, openai_compatible_chat
from ..schemas import ProviderResponse


class OpenRouterProvider(BaseProvider):
    name = "openrouter"
    default_model = "qwen/qwen3-coder:free"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        return await openai_compatible_chat(
            url="https://openrouter.ai/api/v1/chat/completions",
            api_key=settings.openrouter_api_key,
            model=model or self.default_model,
            prompt=prompt,
            provider_name=self.name,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.3),
            timeout=kwargs.get("timeout", 60.0),
            extra_headers={
                "HTTP-Referer": "https://abs.automatiabcn.com",
                "X-Title": "Automatia ABS",
            },
        )
