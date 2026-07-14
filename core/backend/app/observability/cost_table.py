# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""LangFuse-compatible custom price tier per provider/model.

Pricing in USD per 1M tokens. Self-host BGE-M3 / Qwen3-Reranker have
zero API cost but a non-zero compute cost we account for via energy
amortisation; production overlay should refresh these monthly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = [
    "PriceEntry",
    "PRICING",
    "estimate_cost_usd",
    "lookup",
    "register",
]


@dataclass(frozen=True, slots=True)
class PriceEntry:
    provider: str
    model: str
    input_per_million_usd: float
    output_per_million_usd: float
    notes: str = ""


# Default pricing snapshot 2026-04-28. Refresh on the 1st of each month.
PRICING: dict[str, PriceEntry] = {
    "groq:llama-3.3-70b-versatile": PriceEntry(
        provider="groq",
        model="llama-3.3-70b-versatile",
        input_per_million_usd=0.59,
        output_per_million_usd=0.79,
    ),
    "groq:openai/gpt-oss-120b": PriceEntry(
        provider="groq",
        model="openai/gpt-oss-120b",
        input_per_million_usd=0.50,
        output_per_million_usd=0.75,
    ),
    "groq:moonshotai/kimi-k2-instruct": PriceEntry(
        provider="groq",
        model="moonshotai/kimi-k2-instruct",
        input_per_million_usd=1.00,
        output_per_million_usd=3.00,
    ),
    "groq:qwen/qwen3-32b": PriceEntry(
        provider="groq",
        model="qwen/qwen3-32b",
        input_per_million_usd=0.29,
        output_per_million_usd=0.59,
    ),
    "anthropic:claude-opus-4": PriceEntry(
        provider="anthropic",
        model="claude-opus-4",
        input_per_million_usd=15.0,
        output_per_million_usd=75.0,
    ),
    "anthropic:claude-sonnet-4": PriceEntry(
        provider="anthropic",
        model="claude-sonnet-4",
        input_per_million_usd=3.0,
        output_per_million_usd=15.0,
    ),
    "anthropic:claude-haiku-4": PriceEntry(
        provider="anthropic",
        model="claude-haiku-4",
        input_per_million_usd=0.80,
        output_per_million_usd=4.0,
    ),
    "cloudflare:moonshotai/kimi-k2.5": PriceEntry(
        provider="cloudflare",
        model="moonshotai/kimi-k2.5",
        input_per_million_usd=0.0,
        output_per_million_usd=0.0,
        notes="cloudflare AI gateway free tier",
    ),
    "cohere:rerank-v3.5": PriceEntry(
        provider="cohere",
        model="rerank-v3.5",
        input_per_million_usd=2.0,
        output_per_million_usd=0.0,
        notes="$2 per 1k searches; approximate per-token mapping",
    ),
    "selfhost:bge-m3": PriceEntry(
        provider="selfhost",
        model="bge-m3",
        input_per_million_usd=0.02,
        output_per_million_usd=0.0,
        notes="energy amortisation (RTX 4090, 0.4 kWh/h, $0.30/kWh)",
    ),
    "selfhost:qwen3-reranker-4b": PriceEntry(
        provider="selfhost",
        model="qwen3-reranker-4b",
        input_per_million_usd=0.05,
        output_per_million_usd=0.0,
        notes="energy amortisation; bench update pending",
    ),
}


def lookup(provider: str, model: str) -> PriceEntry | None:
    return PRICING.get(f"{provider}:{model}")


def register(entry: PriceEntry) -> None:
    PRICING[f"{entry.provider}:{entry.model}"] = entry
    logger.info("cost_table_register %s:%s", entry.provider, entry.model)


def estimate_cost_usd(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    entry = lookup(provider, model)
    if entry is None:
        logger.debug("cost_table_miss provider=%s model=%s", provider, model)
        return 0.0
    return (
        entry.input_per_million_usd * input_tokens / 1_000_000.0
        + entry.output_per_million_usd * output_tokens / 1_000_000.0
    )
