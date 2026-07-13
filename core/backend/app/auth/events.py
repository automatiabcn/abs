# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-008 — Auth lifecycle events (NATS publish).

Publishes user.registered / user.login.success / user.login.failed envelopes
to JetStream subjects consumed by the Inngest bridge in
`app.worker.nats_bridge`. Failures are swallowed so the auth flow never
crashes because the event bus is degraded.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from app.event_bus import publish as nats_publish

PUBLISH_TIMEOUT_SECONDS = 2.0

logger = logging.getLogger(__name__)

EVENT_SUBJECTS: Mapping[str, str] = {
    "user.registered": "abs.events.user.registered",
    "user.login.success": "abs.events.user.login.success",
    "user.login.failed": "abs.events.user.login.failed",
}

__all__ = [
    "EVENT_SUBJECTS",
    "publish_user_registered",
    "publish_login_success",
    "publish_login_failed",
]


def _iso8601_utc_millis(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _build_envelope(
    event_type: str,
    data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_id": uuid.uuid4().hex,
        "event_type": event_type,
        "occurred_at": _iso8601_utc_millis(datetime.now(timezone.utc)),
        "source": "abs-backend",
        "data": data,
        "metadata": dict(metadata or {}),
    }


async def _safe_publish(subject: str, envelope: dict[str, Any], *, log_ctx: str) -> str:
    try:
        seq = await asyncio.wait_for(
            nats_publish(subject, envelope), timeout=PUBLISH_TIMEOUT_SECONDS
        )
        return str(seq)
    except asyncio.TimeoutError:
        logger.warning(
            "auth_event_publish_timeout %s after %.1fs",
            log_ctx,
            PUBLISH_TIMEOUT_SECONDS,
        )
        return ""
    except Exception as exc:  # noqa: BLE001 — bus boundary
        logger.warning("auth_event_publish_failed %s: %s", log_ctx, exc)
        return ""


async def publish_user_registered(
    user_id: str,
    *,
    email: str,
    tenant_id: str | None = None,
    source: str = "oauth",
    metadata: dict[str, Any] | None = None,
) -> str:
    data: dict[str, Any] = {"user_id": user_id, "email": email, "source": source}
    if tenant_id is not None:
        data["tenant_id"] = tenant_id
    return await _safe_publish(
        EVENT_SUBJECTS["user.registered"],
        _build_envelope("user.registered", data, metadata),
        log_ctx=f"user.registered user_id={user_id}",
    )


async def publish_login_success(
    user_id: str,
    *,
    client_id: str,
    tenant_id: str | None = None,
    scope: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    data: dict[str, Any] = {
        "user_id": user_id,
        "client_id": client_id,
        "scope": scope,
    }
    if tenant_id is not None:
        data["tenant_id"] = tenant_id
    return await _safe_publish(
        EVENT_SUBJECTS["user.login.success"],
        _build_envelope("user.login.success", data, metadata),
        log_ctx=f"user.login.success user_id={user_id} client_id={client_id}",
    )


async def publish_login_failed(
    *,
    client_id: str,
    reason: str,
    user_subject: str | None = None,
    error_code: str = "invalid_grant",
    metadata: dict[str, Any] | None = None,
) -> str:
    data: dict[str, Any] = {
        "client_id": client_id,
        "reason": reason,
        "error_code": error_code,
    }
    if user_subject is not None:
        data["user_subject"] = user_subject
    return await _safe_publish(
        EVENT_SUBJECTS["user.login.failed"],
        _build_envelope("user.login.failed", data, metadata),
        log_ctx=f"user.login.failed client_id={client_id} reason={reason}",
    )
