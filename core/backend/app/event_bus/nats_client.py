# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""NATS JetStream client wrapper.

Used by Inngest worker, auth events, RAG ingest, meeting pipeline.
Singleton connection + JetStream context with idempotent stream
management, JSON-aware publish, error-safe subscribe.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Awaitable, Callable

import nats
from nats.aio.client import Client as NATS
from nats.js.api import RetentionPolicy, StreamConfig
from nats.js.errors import BadRequestError

from app.config import settings

if TYPE_CHECKING:
    from nats.aio.msg import Msg
    from nats.js.client import JetStreamContext
    from nats.js.subscription import JetStreamSubscription

logger = logging.getLogger(__name__)

__all__ = [
    "close",
    "ensure_stream",
    "get_jetstream",
    "get_nats",
    "publish",
    "subscribe",
]

_nc: NATS | None = None
_js: "JetStreamContext | None" = None
_lock = asyncio.Lock()

_RETENTION_MAP = {
    "limits": RetentionPolicy.LIMITS,
    "interest": RetentionPolicy.INTEREST,
    "work_queue": RetentionPolicy.WORK_QUEUE,
}


async def get_nats() -> NATS:
    global _nc
    if _nc is not None and _nc.is_connected:
        return _nc

    async with _lock:
        if _nc is not None and _nc.is_connected:
            return _nc

        url = getattr(settings, "nats_url", "nats://nats:4222")
        _nc = await nats.connect(
            url,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
        )
        logger.info("Connected to NATS at %s", url)
    return _nc


async def get_jetstream() -> "JetStreamContext":
    global _js
    if _js is not None:
        return _js
    nc = await get_nats()
    _js = nc.jetstream()
    return _js


async def ensure_stream(
    name: str,
    subjects: list[str],
    retention: str = "limits",
    max_msgs: int = 1_000_000,
    max_age_seconds: int = 7 * 24 * 3600,
) -> None:
    js = await get_jetstream()

    config = StreamConfig(
        name=name,
        subjects=subjects,
        retention=_RETENTION_MAP.get(retention, RetentionPolicy.LIMITS),
        max_msgs=max_msgs,
        max_age=max_age_seconds,
    )

    try:
        await js.add_stream(config)
        logger.info("Created stream %s subjects=%s", name, subjects)
    except BadRequestError as e:
        if "already" in str(e).lower() or "exists" in str(e).lower():
            await js.update_stream(config)
            logger.info("Updated stream %s subjects=%s", name, subjects)
        else:
            logger.error("Failed to create stream %s: %s", name, e)
            raise


async def publish(
    subject: str,
    payload: dict | bytes,
    *,
    headers: dict[str, str] | None = None,
    stream: str | None = None,
) -> int:
    js = await get_jetstream()

    if isinstance(payload, dict):
        data = json.dumps(payload, separators=(",", ":")).encode()
    else:
        data = payload

    kwargs: dict = {"headers": headers}
    if stream is not None:
        kwargs["stream"] = stream
    ack = await js.publish(subject, data, **kwargs)
    logger.debug("Published to %s seq=%s", subject, getattr(ack, "seq", "?"))
    return int(ack.seq)


async def subscribe(
    subject: str,
    handler: Callable[["Msg"], Awaitable[None]],
    *,
    durable: str | None = None,
    queue: str | None = None,
    manual_ack: bool = True,
) -> "JetStreamSubscription":
    js = await get_jetstream()

    async def _wrapper(msg: "Msg") -> None:
        try:
            await handler(msg)
            if manual_ack:
                await msg.ack()
        except Exception as exc:  # noqa: BLE001 — bus boundary
            logger.error("Handler failed for %s: %s", subject, exc, exc_info=True)
            if manual_ack:
                try:
                    await msg.nak()
                except Exception:  # noqa: BLE001
                    logger.exception("nak() failed for %s", subject)

    sub_kwargs: dict = {"cb": _wrapper, "manual_ack": manual_ack}
    if durable is not None:
        sub_kwargs["durable"] = durable
    if queue is not None:
        sub_kwargs["queue"] = queue
    sub = await js.subscribe(subject, **sub_kwargs)
    logger.info("Subscribed to %s durable=%s queue=%s", subject, durable, queue)
    return sub


async def close() -> None:
    global _nc, _js
    try:
        if _nc is not None:
            try:
                await _nc.drain()
            except Exception:  # noqa: BLE001
                logger.exception("NATS drain failed")
            try:
                await _nc.close()
            except Exception:  # noqa: BLE001
                logger.exception("NATS close failed")
            logger.info("NATS connection closed")
    finally:
        _nc = None
        _js = None
