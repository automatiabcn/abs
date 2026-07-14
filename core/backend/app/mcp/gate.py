# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The licence gate on MCP tool calls.

  - `_gate_status() -> dict` — where the install stands right now
    (license_active, demo_active, allowed)
  - `with_gate(tool_name) -> decorator` — wrap a single tool

The `with_hooks` decorator calls `_gate_status()` on every tool call. When
`mcp_require_license` is on and the gate says no, the tool does not run and the
caller gets `_BLOCK_MESSAGE` instead — a refusal that says why, rather than a
tool that quietly does nothing.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Dict

from app.config import settings

logger = logging.getLogger(__name__)


_BLOCK_MESSAGE = (
    "[SUBSCRIPTION REQUIRED] This ABS server is not on an active subscription — "
    "the seven-day trial has ended, or the licence has lapsed. Tools are paused. "
    "Everything on the server is still yours: documents, transcripts and keys can "
    "be read, exported and deleted from the panel. Subscribe under "
    "Settings → Licence."
)


def _gate_status() -> Dict[str, Any]:
    """Where this install stands, asked of the one place that knows.

    This module used to answer the question itself: its own signature check, its
    own expiry check, its own revocation query against the database. Two
    implementations of the same rule drift, and these two already had — the chat
    gate learned about grace windows, offline verdicts and, now, the trial, while
    this one still only knew "is there a key that parses". A customer on day three
    of their trial would have been refused by their editor and served by their
    panel, and both would have been telling the truth as they understood it.

    One rule, one place: `app.licensing.gate`.
    """
    from app.licensing import gate as licence_gate

    # Two questions, and they are not the same one.
    #
    # `enforce()` decides whether this request runs, and it reads the escape
    # hatches (ABS_TEST_MODE, ABS_LICENSE_GATE_DISABLED) — that is their job.
    # `evaluate()` says where the install actually stands, and the fields below
    # that *describe* it are read from that, because a bypass may excuse a server
    # from the rule but it must never let the server lie about itself. The
    # licence page learned this the hard way: it read through the hatch and told
    # a customer a junk key was "licensed".
    decision = licence_gate.enforce()
    truth = licence_gate.evaluate()
    verdict = truth.verdict

    return {
        "license_active": verdict is licence_gate.Verdict.LICENSED,
        "trial_active": verdict is licence_gate.Verdict.TRIAL,
        # Kept for the SSE banner, which has asked this question since before the
        # free window was called a trial. It is the same window now.
        "demo_active": verdict is licence_gate.Verdict.TRIAL,
        # `mcp_require_license` stays as the operator's switch — an air-gapped
        # install with a site licence may want the tools open regardless — but it
        # is no longer the reason a subscription is optional. Its default is now
        # on: tools are the product, and the product is a subscription.
        "allowed": (not settings.mcp_require_license) or decision.allowed,
        "require_license": settings.mcp_require_license,
        "verdict": verdict.value,
        "detail": "" if decision.allowed else decision.detail,
    }


def with_gate(tool_name: str) -> Callable:
    """Opsiyonel — tek-tool gate sarmalayici (with_hooks zaten icinde cagiriyor)."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            s = _gate_status()
            if not s["allowed"]:
                return _BLOCK_MESSAGE
            return await fn(*args, **kwargs)

        return wrapper

    return decorator
