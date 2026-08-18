# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Provider registry — name → instance singleton."""

from __future__ import annotations

from typing import Dict

from .anthropic import AnthropicProvider
from .base import BaseProvider
from .cerebras import CerebrasProvider
from .cloudflare import CloudflareProvider
from .cohere import CohereProvider
from .gemini import GeminiProvider
from .groq import GroqProvider
from .mlx import MLXProvider
from .ollama import OllamaProvider
from .openrouter.adapter import OpenRouterProvider

_registry: Dict[str, BaseProvider] = {}


def get_registry() -> Dict[str, BaseProvider]:
    if not _registry:
        _registry["anthropic"] = AnthropicProvider()
        _registry["groq"] = GroqProvider()
        _registry["cerebras"] = CerebrasProvider()
        _registry["gemini"] = GeminiProvider()
        _registry["cloudflare"] = CloudflareProvider()
        _registry["cohere"] = CohereProvider()
        _registry["ollama"] = OllamaProvider()
        _registry["mlx"] = MLXProvider()  # Apple Silicon Neural Engine
        # Was never registered: openrouter sat in every PROVIDER_ORDER as the
        # paid lane and get_provider raised "unknown provider" for it — a
        # second dead lane behind the missing settings key (2026-08-18).
        _registry["openrouter"] = OpenRouterProvider()
    return _registry


def get_provider(name: str) -> BaseProvider:
    reg = get_registry()
    if name not in reg:
        raise KeyError(f"Bilinmeyen provider: {name}")
    return reg[name]
