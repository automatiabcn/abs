# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Anthropic Messages API v1 surface markers.

Versioned request/response shape lives in `contracts/{request,response}_v1.json`
(T-S02.2 golden fixtures). The actual httpx call is in adapter.py.
"""

from __future__ import annotations

API_VERSION: str = "v1"
SUPPORTED_MODELS: tuple[str, ...] = (
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
)
