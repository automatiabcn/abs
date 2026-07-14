# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""OpenRouter provider package — hexagonal layout."""

from .adapter import OpenRouterProvider

__all__ = ["OpenRouterProvider"]
API_VERSIONS = ("v1",)
