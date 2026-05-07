# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Anthropic Messages API v2 surface (tool_use blocks, server-side tools).

The v2 contract is forward-compatible: v1 callers keep working because
adapter.py emits a v1 request unless tools are present.
"""

from __future__ import annotations

API_VERSION: str = "v2"
SUPPORTS_TOOL_USE: bool = True
SUPPORTS_PARALLEL_TOOL_CALLS: bool = True
