# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Anthropic provider — Claude Haiku/Sonnet/Opus.

Uses the `anthropic>=0.40` async SDK. The SDK is an optional dependency: a
missing package surfaces as a non-transient ProviderError, not an ImportError,
so an install without it degrades instead of crashing.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from app.config import settings

from ..base import BaseProvider
from ..schemas import ProviderError, ProviderResponse


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    default_model = "claude-haiku-4-5-20251001"

    async def call(
        self,
        prompt: str,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        # Anthropic is the one paid provider — opt-in, so a free-tier install
        # can never reach the network from here.
        if not bool(getattr(settings, "anthropic_enabled", False)):
            raise ProviderError(
                "Anthropic provider is opt-in; set ABS_ANTHROPIC_ENABLED=true to enable",
                provider=self.name,
                transient=False,
            )
        _key = kwargs.get("api_key") or settings.anthropic_api_key
        if not _key:
            raise ProviderError(
                "Anthropic API key is not configured", provider=self.name, transient=False
            )

        # Quota gate runs BEFORE the network call — the budget must be enforced
        # by refusing to spend, not by noticing afterwards.
        from app.observability import quota_monitor as _qm

        try:
            _qm.gate(requested_tokens=int(kwargs.get("max_tokens", 1024)))
        except _qm.QuotaExceeded as exc:
            raise ProviderError(
                f"Anthropic blocked by quota gate: {exc}",
                provider=self.name,
                transient=True,
            ) from exc

        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ProviderError(
                "anthropic package is not installed",
                provider=self.name,
                transient=False,
            ) from exc

        client = AsyncAnthropic(api_key=_key)
        model = model or self.default_model
        max_tokens = kwargs.get("max_tokens", 1024)
        timeout = kwargs.get("timeout", 60.0)

        start = time.monotonic()
        try:
            msg = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
            )
        except Exception as exc:
            name = type(exc).__name__
            transient = name in {"RateLimitError", "APITimeoutError", "APIConnectionError"} or "500" in str(exc)
            raise ProviderError(
                f"Anthropic {name}: {str(exc)[:200]}",
                provider=self.name,
                transient=transient,
            ) from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        text_parts = []
        for block in getattr(msg, "content", []) or []:
            t = getattr(block, "text", None)
            if t:
                text_parts.append(t)
        text = "".join(text_parts)

        usage = getattr(msg, "usage", None)
        tokens_in = getattr(usage, "input_tokens", None) if usage else None
        tokens_out = getattr(usage, "output_tokens", None) if usage else None

        # Feed the monthly budget tracker.
        from app.observability import quota_monitor as _qm

        try:
            _qm.record(
                tokens_in=int(tokens_in or 0),
                tokens_out=int(tokens_out or 0),
                model=model,
            )
        except Exception:  # pragma: no cover — never fail the call on ledger error
            pass

        return ProviderResponse(
            text=text,
            model=model,
            provider=self.name,
            elapsed_ms=elapsed_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
