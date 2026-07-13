# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Event bus package (NATS JetStream)."""

from app.event_bus.nats_client import (
    close,
    ensure_stream,
    get_jetstream,
    get_nats,
    publish,
    subscribe,
)

__all__ = [
    "close",
    "ensure_stream",
    "get_jetstream",
    "get_nats",
    "publish",
    "subscribe",
]
