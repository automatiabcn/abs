# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Gemini provider package — hexagonal layout (T-S02.1)."""

from .adapter import GeminiProvider

__all__ = ["GeminiProvider"]
API_VERSIONS = ("v1", "v1beta")
