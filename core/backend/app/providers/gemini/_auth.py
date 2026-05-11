# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Gemini auth — `x-goog-api-key` header constructor (replaces `?key=` query
param to avoid plaintext leakage in HTTP request logs).

Reference: https://ai.google.dev/api/rest/v1beta/models — Gemini REST accepts
either query param or header; header form keeps the secret out of URLs.
"""

from __future__ import annotations

from typing import Dict


def gemini_headers(api_key: str, *, json: bool = True) -> Dict[str, str]:
    """Return canonical Gemini auth headers.

    Always sets `x-goog-api-key`. Adds `Content-Type: application/json` when
    `json=True` (most generateContent calls).
    """
    headers: Dict[str, str] = {"x-goog-api-key": api_key}
    if json:
        headers["Content-Type"] = "application/json"
    return headers
