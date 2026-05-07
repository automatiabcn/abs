# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""033 Modul C — Provider mock layer for demo mode.

When `settings.provider_mock` is True, deterministic responses replace
live HTTP calls. Latency is simulated to look realistic on screen recording.

Public API (synchronous façade — providers/orchestrator import these):
    - mock_openai_chat(model, prompt) → ProviderResponse
    - mock_anthropic_message(model, prompt) → ProviderResponse
    - mock_stripe_event(event_type) → dict
    - mock_github_oauth_token(code) → dict
    - mock_slack_post(channel, text) → dict
    - mock_cohere_rerank(query, docs) → list[dict]
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from app.providers.schemas import ProviderResponse

LOREM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Mock response generated for demo mode — this is not a live LLM call."
)


async def _simulate_latency(low_ms: int, high_ms: int) -> None:
    await asyncio.sleep(random.uniform(low_ms, high_ms) / 1000.0)


async def mock_openai_chat(
    model: str, prompt: str, latency_range: tuple[int, int] = (200, 400)
) -> ProviderResponse:
    """Mock Groq/OpenAI/Cerebras/Cloudflare style response."""
    await _simulate_latency(*latency_range)
    text = f"[mock:{model}] {LOREM[:120]}"
    return ProviderResponse(
        text=text,
        provider="mock",
        model=model,
        tokens_in=len(prompt.split()),
        tokens_out=len(text.split()),
    )


async def mock_anthropic_message(
    model: str, prompt: str
) -> ProviderResponse:
    return await mock_openai_chat(
        model=model, prompt=prompt, latency_range=(800, 1200)
    )


def mock_stripe_event(event_type: str = "checkout.session.completed") -> dict[str, Any]:
    return {
        "id": "evt_mock_" + str(random.randint(10**6, 10**7)),
        "object": "event",
        "type": event_type,
        "data": {
            "object": {
                "id": "cs_test_mock",
                "customer_email": "demo@meetingco.test",
                "amount_total": 29900,
                "currency": "usd",
            }
        },
        "livemode": False,
    }


def mock_github_oauth_token(code: str) -> dict[str, Any]:
    return {
        "access_token": "ghs_mock_" + code[:10],
        "token_type": "bearer",
        "scope": "repo user:email",
        "expires_in": 28800,
    }


def mock_slack_post(channel: str, text: str) -> dict[str, Any]:
    return {
        "ok": True,
        "channel": channel,
        "ts": str(random.randint(10**9, 10**10)) + ".000100",
        "message": {"text": text},
    }


def mock_cohere_rerank(query: str, docs: list[str]) -> list[dict[str, Any]]:
    """Static rerank — score by document length, descending."""
    return [
        {"index": i, "relevance_score": min(1.0, len(d) / 200)}
        for i, d in sorted(enumerate(docs), key=lambda kv: -len(kv[1]))
    ]
