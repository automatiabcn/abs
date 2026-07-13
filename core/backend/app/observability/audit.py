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

import json as _json
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


# Set once the audit write has failed, so the traceback is printed once rather
# than on every request for as long as the database is unreachable.
_persist_broken = False


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
    _persist(payload)


def _persist(payload: dict[str, Any]) -> None:
    """Write the event into the signed chain the panel actually reads.

    Without this, `emit_event` was a monologue. It logged to `abs.audit`, a
    logger with no handler anywhere in the codebase, so the record propagated to
    root, printed the literal word "audit" — no formatter reads `extra` — and the
    payload was dropped on the floor. Meanwhile `/v1/admin/audit/recent` and the
    chain verifier read database tables that almost nothing wrote to.

    Two audit systems, back to back, never touching. The panel showed sample rows
    when its query came back empty, which it always did, so the log looked alive
    for as long as nobody looked twice: on a real server, every login, every
    provider key changed, every approval decided was recorded nowhere a person
    could ever retrieve it.

    Best-effort on purpose. An audit write that fails must not take the request
    down with it — but it must also not fail *silently*, so the failure is logged
    at warning. A quiet recorder is how this happened in the first place.

    Cost, measured rather than assumed: ~1 ms per event against SQLite. That is
    invisible next to a request, so the write stays synchronous. Handing it to a
    queue would buy nothing and would reintroduce the exact failure being fixed —
    an event that is "sent" and never lands.
    """
    global _persist_broken  # noqa: PLW0603

    try:
        from app.vault.audit_chain import append_entry

        detail = {
            k: v
            for k, v in payload.items()
            if k not in ("action", "ts", "tenant_id", "user_id")
        }
        append_entry(
            # The column is 32 chars. Truncating is right — a truncated action is
            # still a row, and a row that fails to insert is the bug we just fixed.
            action=str(payload.get("action", "unknown"))[:32],
            actor=str(payload.get("user_id") or "system")[:64],
            target_key=(str(payload["path"])[:128] if payload.get("path") else None),
            detail=_json.dumps(detail, default=str)[:512],
            tenant_id=(str(payload["tenant_id"])[:64] if payload.get("tenant_id") else None),
        )
        # Recovered. Re-arm the traceback, so the *next* outage is diagnosable too
        # rather than being written off as more of the last one.
        _persist_broken = False
    except Exception as exc:  # noqa: BLE001 — never fail a request over its own audit trail
        if not _persist_broken:
            # The first one carries the traceback, because somebody has to be able
            # to diagnose it.
            _persist_broken = True
            _logger().warning("audit event could not be recorded", exc_info=True)
        else:
            # The rest do not. If the database is gone, this fires on every single
            # request, and a full traceback per request buries the very log a person
            # would be reading to find out why. Still loud, still every time — never
            # silent, because silence is the bug this whole module is an apology for.
            _logger().warning("audit event could not be recorded: %s", exc)
