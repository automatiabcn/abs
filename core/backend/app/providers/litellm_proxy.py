"""LiteLLM proxy adapter — optional gateway in front of native ABS providers.

Sprint 19 T-S02.4 — POC. Disabled by default; enable by setting
`ABS_LITELLM_PROXY_URL` (e.g., `http://litellm-proxy:4000`). When enabled,
ABS routes all chat completions through the LiteLLM proxy instead of native
provider adapters.

This is intentionally tiny: LiteLLM speaks an OpenAI-compatible /v1/chat/completions
shape, so we reuse `openai_compatible_chat`. The trade-off vs native
adapter.py modules is documented in `docs/architecture/litellm-vs-native.md`.

Native ABS providers stay the canonical path. The LiteLLM layer is opt-in
infrastructure (e.g., for orgs that already run a LiteLLM gateway for cost
budgeting + per-key rate-limit dashboards).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .base import BaseProvider, openai_compatible_chat
from .schemas import ProviderError, ProviderResponse


def is_enabled() -> bool:
    return bool(os.getenv("ABS_LITELLM_PROXY_URL"))


class LiteLLMProxyProvider(BaseProvider):
    """Routes calls through a LiteLLM proxy when enabled."""

    name = "litellm_proxy"
    default_model = "groq/llama-3.1-8b-instant"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        url = os.getenv("ABS_LITELLM_PROXY_URL")
        if not url:
            raise ProviderError(
                "LiteLLM proxy disabled (set ABS_LITELLM_PROXY_URL to enable)",
                provider=self.name,
                transient=False,
            )

        api_key = os.getenv("ABS_LITELLM_API_KEY", "litellm-anonymous")
        return await openai_compatible_chat(
            url=f"{url.rstrip('/')}/v1/chat/completions",
            api_key=api_key,
            model=model or self.default_model,
            prompt=prompt,
            provider_name=self.name,
            max_tokens=kwargs.get("max_tokens", 1024),
            temperature=kwargs.get("temperature", 0.3),
            timeout=kwargs.get("timeout", 60.0),
        )


__all__ = ["LiteLLMProxyProvider", "is_enabled"]
