"""OpenRouter v2 — reserved for future Anthropic-style tool_use surface.

Currently a marker module so the hexagonal layout is symmetric across providers.
"""

from __future__ import annotations

API_VERSION: str = "v2"
SUPPORTS_TOOL_USE: bool = False  # OpenRouter normalises to OpenAI tool_calls today
