# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Groq OpenAI-compatible chat completions v1."""

from __future__ import annotations

API_VERSION: str = "v1"
SUPPORTED_MODELS: tuple[str, ...] = (
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "moonshotai/kimi-k2-instruct",
    "qwen/qwen3-32b",
)
