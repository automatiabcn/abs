# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Cohere v1 surface — chat, embed, rerank pre-V2."""

from __future__ import annotations

API_VERSION: str = "v1"
SUPPORTED_MODELS: tuple[str, ...] = (
    "command-r",
    "command-r-plus",
    "embed-english-v3.0",
    "rerank-multilingual-v3.0",
)
