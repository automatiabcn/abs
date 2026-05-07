# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Q12-L23 — structured audit emit helper.

Single entry point for emitting *security/operability-relevant* events
to the `abs.audit` logger. Pairs with `RequestIDMiddleware` so every
event carries a `request_id` that lets ops correlate a stack-trace,
a log line, a metric counter, and a user incident report.

Convention:

    from app.observability.audit import emit_event

    @router.post("/login")
    def login(request: Request, ...):
        try:
            ...
        except ExpiredSignatureError:
            emit_event(
                request,
                action="auth.session.decode",
                outcome="denied",
                reason="expired",
            )
            raise HTTPException(401, "session_expired")

`outcome` is restricted to {success, failure, denied, error}.

PII guard-rail: the `**ctx` allowlist drops any unknown key whose name
matches a sensitive prefix (`password*`, `secret*`, `api_key*`,
`token*`, `cookie*`, `authorization*`). Add new safe fields to
`SAFE_KEYS` instead of routing PII through ctx.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Final

from starlette.requests import Request

LOGGER_NAME: Final[str] = "abs.audit"
ALLOWED_OUTCOMES: Final[frozenset[str]] = frozenset(
    {"success", "failure", "denied", "error"}
)

# Allowlist of *safe* context keys — anything else is dropped silently.
SAFE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "reason",
        "resource_id",
        "resource_type",
        "ip",
        "user_agent",
        "method",
        "path",
        "status_code",
        "tenant_id",
        "user_id",
        "email_hint",  # masked (only first 3 chars)
        "provider",
        "duration_ms",
        "count",
        "error_class",
    }
)

_SENSITIVE_PREFIXES = (
    "password",
    "secret",
    "api_key",
    "token",
    "cookie",
    "authorization",
    "bearer",
    "private",
)


def _logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def _scrub(ctx: dict[str, Any]) -> dict[str, Any]:
    """Drop sensitive keys; keep allowlisted ones."""
    safe: dict[str, Any] = {}
    for key, value in ctx.items():
        lk = key.lower()
        if any(lk.startswith(p) for p in _SENSITIVE_PREFIXES):
            continue
        if key not in SAFE_KEYS:
            continue
        safe[key] = value
    return safe


def emit_event(
    request: Request | None,
    *,
    action: str,
    outcome: str,
    **ctx: Any,
) -> None:
    """Emit one structured audit event.

    Args:
        request: incoming Request (used to lift request_id, tenant_id,
            user_id off `request.state` if present). Pass `None` from
            background tasks; supply `tenant_id`/`user_id` via ctx.
        action: dotted name (e.g. "auth.login", "rag.query",
            "vault.secret.read"). NOT user-controlled.
        outcome: one of `ALLOWED_OUTCOMES`.
        **ctx: extra fields, scrubbed against `SAFE_KEYS`.
    """
    if outcome not in ALLOWED_OUTCOMES:
        outcome = "error"
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "outcome": outcome,
    }
    if request is not None:
        state = request.state
        for fld in ("request_id", "tenant_id", "user_id"):
            val = getattr(state, fld, None)
            if val is not None:
                payload[fld] = val
        payload.setdefault("method", request.method)
        payload.setdefault("path", request.url.path)
    payload.update(_scrub(ctx))
    _logger().info("audit", extra={"audit": payload})
