# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""OpenRouter v1 surface — OpenAI-compatible passthrough."""

from __future__ import annotations

API_VERSION: str = "v1"
SUPPORTED_MODELS: tuple[str, ...] = (
    "qwen/qwen3-coder:free",
    "deepseek/deepseek-r1:free",
    "google/gemma-3-27b-it:free",
    "minimax/minimax-m2:free",
)
