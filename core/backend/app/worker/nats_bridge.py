# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-002 — NATS → Inngest bridge.

Subscribes to durable NATS subjects and forwards each message as an
Inngest event. Decouples internal services (which only know NATS) from
the durable workflow engine.

Subject mapping (extend as new domains land):
    abs.events.user.registered      -> inngest event "abs/user.registered"
    abs.events.user.login.success   -> inngest event "abs/user.login.success"
    abs.events.user.login.failed    -> inngest event "abs/user.login.failed"
"""

from __future__ import annotations

import json
import logging
from typing import Iterable

import inngest

from app.event_bus import ensure_stream, subscribe
from app.worker.inngest_app import inngest_client

logger = logging.getLogger(__name__)

__all__ = ["DEFAULT_SUBJECT_MAP", "bridge_nats_to_inngest"]

DEFAULT_SUBJECT_MAP: dict[str, str] = {
    "abs.events.user.registered": "abs/user.registered",
    "abs.events.user.login.success": "abs/user.login.success",
    "abs.events.user.login.failed": "abs/user.login.failed",
}


def _decode(raw: bytes) -> dict:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"expected object payload, got {type(payload).__name__}")
    return payload


async def bridge_nats_to_inngest(
    *,
    stream: str = "ABS_EVENTS",
    stream_subjects: Iterable[str] = ("abs.events.>",),
    subject_map: dict[str, str] | None = None,
    durable_prefix: str = "abs-bridge",
) -> list:
    """Wire NATS subscribers that forward to Inngest. Returns the
    JetStream subscription handles so callers can unsubscribe on shutdown.
    """

    mapping = subject_map or DEFAULT_SUBJECT_MAP
    await ensure_stream(stream, list(stream_subjects))

    subs = []
    for nats_subject, inngest_event in mapping.items():
        durable = f"{durable_prefix}-{inngest_event.replace('/', '_').replace('.', '_')}"

        async def _handler(msg, _evt=inngest_event) -> None:  # noqa: ANN001
            data = _decode(msg.data)
            await inngest_client.send(
                inngest.Event(name=_evt, data=data)
            )
            logger.debug("nats→inngest forwarded %s -> %s", msg.subject, _evt)

        sub = await subscribe(nats_subject, _handler, durable=durable)
        subs.append(sub)
        logger.info(
            "nats→inngest bridge ready subject=%s -> event=%s durable=%s",
            nats_subject,
            inngest_event,
            durable,
        )
    return subs
