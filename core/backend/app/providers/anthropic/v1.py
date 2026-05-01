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
