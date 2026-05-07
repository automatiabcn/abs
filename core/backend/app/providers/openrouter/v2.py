# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""OpenRouter v2 — reserved for future Anthropic-style tool_use surface.

Currently a marker module so the hexagonal layout is symmetric across providers.
"""

from __future__ import annotations

API_VERSION: str = "v2"
SUPPORTS_TOOL_USE: bool = False  # OpenRouter normalises to OpenAI tool_calls today
