# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Slack webhook signing verification.

Slack signs every events_api callback with:

  X-Slack-Signature: v0=<hex_hmac>
  X-Slack-Request-Timestamp: <unix_ts>

  v0 = HMAC-SHA256(signing_secret, "v0:" + timestamp + ":" + body)

Security:
  - Reject if timestamp older than 5 minutes (replay attack guard).
  - Use `hmac.compare_digest` for constant-time compare.
  - Reject if signing_secret is empty (boot fail-safe).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Tuple

logger = logging.getLogger(__name__)


_REPLAY_WINDOW_SECONDS = 5 * 60  # 5 minutes


def verify_slack_signature(
    *,
    signing_secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
    now_ts: int | None = None,
) -> Tuple[bool, str]:
    """Verify a Slack request signature.

    Returns: (ok, reason). `reason` is empty when ok=True.
    """
    if not signing_secret:
        return False, "signing_secret_empty"
    if not timestamp or not signature:
        return False, "header_missing"
    try:
        ts = int(timestamp)
    except ValueError:
        return False, "timestamp_invalid"

    now = now_ts if now_ts is not None else int(time.time())
    if abs(now - ts) > _REPLAY_WINDOW_SECONDS:
        return False, "timestamp_expired"

    base_string = b"v0:" + timestamp.encode("ascii") + b":" + body
    expected = (
        "v0="
        + hmac.new(
            signing_secret.encode("utf-8"),
            base_string,
            hashlib.sha256,
        ).hexdigest()
    )
    if hmac.compare_digest(expected, signature):
        return True, ""
    return False, "signature_mismatch"
