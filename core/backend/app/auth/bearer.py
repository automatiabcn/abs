# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Shared bearer-token extraction and constant-time verification.

The admin bearer endpoints (vault key rotation, demo reset, smart-link
admin) each compared the presented token with ``!=``, which short-circuits
on the first differing byte and leaks the shared secret's prefix through
response timing. The MCP token path already used ``hmac.compare_digest``;
this module gives every bearer surface the same guarantee from one place.
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import HTTPException


def extract_bearer(authorization: Optional[str]) -> str:
    """Return the token from an ``Authorization: Bearer <token>`` header.

    Raises 401 when the header is missing or is not a bearer scheme.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token expected")
    return authorization.split(None, 1)[1].strip()


def token_matches(presented: str, expected: Optional[str]) -> bool:
    """Constant-time equality. An unset/empty ``expected`` never matches."""
    if not expected:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))
