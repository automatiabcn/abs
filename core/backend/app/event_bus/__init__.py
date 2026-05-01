"""T-001 — Event bus package (NATS JetStream)."""

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
