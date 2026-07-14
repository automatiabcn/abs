# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Inngest client + first durable function (on_user_registered).

Triggered by `abs/user.registered` Inngest events that are forwarded from
the NATS subject `abs.events.user.registered` by `nats_bridge.py`.

Retry policy: exponential backoff via Inngest SDK defaults (4 attempts,
30s..2h cap). Failures route to Inngest DLQ.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

import inngest

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = ["functions", "inngest_client", "on_user_registered"]


inngest_client = inngest.Inngest(
    app_id="abs-backend",
    is_production=(settings.env == "prod"),
    logger=logger,
)


@inngest_client.create_function(
    fn_id="on_user_registered",
    trigger=inngest.TriggerEvent(event="abs/user.registered"),
    retries=4,
)
async def on_user_registered(
    ctx: inngest.Context,
) -> dict[str, Any]:
    """Handle freshly registered users.

    Steps are individually retried/cached by Inngest:
      1. `validate-payload` — guard required fields, unrecoverable error fails fast.
      2. `record-onboarding` — idempotent side-effect placeholder (a later round wires
         email queue + audit log + RAG profile bootstrap).
    """

    event = ctx.event
    data: dict[str, Any] = dict(event.data or {})

    async def _validate() -> dict[str, Any]:
        user_id = data.get("user_id")
        email = data.get("email")
        if not user_id or not email:
            raise inngest.NonRetriableError(f"missing user_id/email in {sorted(data)}")
        return {"user_id": str(user_id), "email": str(email)}

    user = await ctx.step.run("validate-payload", _validate)

    async def _record() -> dict[str, Any]:
        # Placeholder. Real onboarding is wired up elsewhere.
        ctx.logger.info(
            "user_registered_received user_id=%s email=%s",
            user["user_id"],
            user["email"],
        )
        return {
            "user_id": user["user_id"],
            "recorded_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }

    return await ctx.step.run("record-onboarding", _record)


functions: list[inngest.Function] = [on_user_registered]
