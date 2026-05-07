# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Phase 3 / Q3 — Mock Anthropic provider for cascade fallback testing.

Lets the cascade chain be exercised end-to-end **without an Anthropic API
key**. Behaviour is configurable via `settings.anthropic_mock_mode`:

* `off`        — disabled. Real (or absent) Anthropic client is used.
* `ok`         — returns a deterministic mock completion immediately.
* `rate_limit` — raises `RateLimitError` so cascade falls through to Groq.
* `timeout`    — raises `TimeoutError` (sleep is short so tests stay fast).
* `provider_500` — raises `ProviderError` (5xx-shape) so cascade falls through.
* `random`     — picks one of {ok, rate_limit, timeout, provider_500}
                 deterministically per call (seeded by request_id when set,
                 else random).

The mock returns a `ProviderResponse`-shaped dict so the cascade adapter
treats it identically to a real Anthropic completion.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Optional

from app.providers.schemas import ProviderError

logger = logging.getLogger(__name__)


VALID_MODES = (
    "off",
    "ok",
    "rate_limit",
    "timeout",
    "provider_500",
    "random",
)


class RateLimitError(ProviderError):
    """Mock 429 — cascade should treat as fallback trigger."""


@dataclass
class MockResponse:
    completion: str
    tokens: int
    provider: str = "anthropic-mock"


class AnthropicMockProvider:
    """Test-only provider — never makes a real network call."""

    def __init__(self, behavior: str = "ok") -> None:
        if behavior not in VALID_MODES or behavior == "off":
            raise ValueError(f"AnthropicMockProvider invalid behavior: {behavior}")
        self.behavior = behavior

    def _resolve_behavior(self, request_id: Optional[str]) -> str:
        if self.behavior != "random":
            return self.behavior
        choices = ("ok", "rate_limit", "timeout", "provider_500")
        if request_id:
            seed = sum(ord(c) for c in request_id)
            return choices[seed % len(choices)]
        return random.choice(choices)

    async def complete(
        self,
        prompt: str,
        *,
        request_id: Optional[str] = None,
    ) -> MockResponse:
        mode = self._resolve_behavior(request_id)
        logger.debug("anthropic_mock complete mode=%s len=%d", mode, len(prompt))

        if mode == "rate_limit":
            raise RateLimitError("anthropic_mock_429: rate limit exceeded")
        if mode == "timeout":
            # Short real sleep so tests don't actually stall — caller should
            # treat this as a TimeoutError equivalent via cascade policy.
            await asyncio.sleep(0.05)
            raise TimeoutError("anthropic_mock_timeout")
        if mode == "provider_500":
            raise ProviderError("anthropic_mock_500: provider unavailable")
        # ok — deterministic echo so tests can match.
        return MockResponse(
            completion=f"[MOCK ANTHROPIC] echo: {prompt[:80]}",
            tokens=max(1, len(prompt) // 4),
        )


def get_mock_provider() -> Optional[AnthropicMockProvider]:
    """Return mock instance if `ABS_ANTHROPIC_MOCK_MODE` is set + non-`off`,
    else None."""
    from app.config import settings

    mode = getattr(settings, "anthropic_mock_mode", "off")
    if mode in ("off", "", None):
        return None
    return AnthropicMockProvider(behavior=mode)


__all__ = [
    "AnthropicMockProvider",
    "MockResponse",
    "RateLimitError",
    "VALID_MODES",
    "get_mock_provider",
]
