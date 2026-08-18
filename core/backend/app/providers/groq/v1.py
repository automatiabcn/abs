# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Groq OpenAI-compatible chat completions v1."""

from __future__ import annotations

API_VERSION: str = "v1"
SUPPORTED_MODELS: tuple[str, ...] = (
    # Live catalogue 2026-08-18. Llama 3.x, Kimi K2 and Qwen3-32B were retired
    # by Groq on 2026-08-16; `providers/catalog_watch.py` compares this tuple
    # with /models on every start.
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "groq/compound",
    "groq/compound-mini",
)
