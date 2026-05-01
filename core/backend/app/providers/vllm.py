"""vLLM provider — self-host cluster (OpenAI-uyumlu)."""

from __future__ import annotations

from typing import Any, Optional

from app.config import settings

from .base import BaseProvider, openai_compatible_chat
from .schemas import ProviderError, ProviderResponse


class VllmProvider(BaseProvider):
    name = "vllm"
    default_model = "default"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        if not settings.vllm_url:
            raise ProviderError(
                "VLLM_URL tanımlı değil", provider=self.name, transient=False
            )
        base = settings.vllm_url.rstrip("/")
        return await openai_compatible_chat(
            url=f"{base}/v1/chat/completions",
            api_key=settings.vllm_api_key or "self-host",  # nosec — self-hosted vLLM ignores it
            model=model or self.default_model,
            prompt=prompt,
            provider_name=self.name,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.3),
            timeout=kwargs.get("timeout", 60.0),
        )
