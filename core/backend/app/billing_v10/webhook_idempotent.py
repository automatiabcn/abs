"""T-044 — Stripe webhook idempotency + replay protection + audit log."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = [
    "ReplayedWebhookError",
    "InvalidWebhookSignature",
    "WebhookEvent",
    "WebhookProcessor",
    "verify_signature",
]


class ReplayedWebhookError(RuntimeError):
    """Raised when an event_id has already been processed."""


class InvalidWebhookSignature(RuntimeError):
    """Raised when the Stripe-Signature header doesn't validate."""


@dataclass(slots=True)
class WebhookEvent:
    event_id: str
    event_type: str
    payload: dict
    received_at: float
    audit_hash: str


def verify_signature(
    *,
    payload_bytes: bytes,
    timestamp: int,
    signature: str,
    secret: str,
    max_age_seconds: int = 300,
) -> None:
    """Mimics Stripe's `t=...,v1=...` signature scheme."""

    if not secret:
        raise InvalidWebhookSignature("webhook secret not configured")
    if abs(time.time() - timestamp) > max_age_seconds:
        raise InvalidWebhookSignature("timestamp outside replay window")
    signed_payload = f"{timestamp}.".encode("ascii") + payload_bytes
    expected = hmac.new(
        secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise InvalidWebhookSignature("signature mismatch")


class WebhookProcessor:
    def __init__(self, *, replay_window_seconds: int = 7 * 86400) -> None:
        self._seen: dict[str, float] = {}
        self._audit: list[dict] = []
        self.replay_window_seconds = replay_window_seconds

    def _audit_hash(self, event_id: str, event_type: str, payload: dict) -> str:
        prev = self._audit[-1]["audit_hash"] if self._audit else ""
        digest = hashlib.sha256(
            f"{prev}|{event_id}|{event_type}|{sorted(payload.items())}".encode(
                "utf-8"
            )
        ).hexdigest()
        return digest

    def process(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: dict,
    ) -> WebhookEvent:
        if not event_id:
            raise ValueError("event_id required")
        seen_at = self._seen.get(event_id)
        if seen_at is not None and (time.time() - seen_at) < self.replay_window_seconds:
            raise ReplayedWebhookError(
                f"event_id {event_id!r} already processed"
            )
        ts = time.time()
        self._seen[event_id] = ts
        record = WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            payload=dict(payload),
            received_at=ts,
            audit_hash=self._audit_hash(event_id, event_type, payload),
        )
        self._audit.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "received_at": ts,
                "audit_hash": record.audit_hash,
            }
        )
        logger.info(
            "stripe_webhook_processed event_id=%s type=%s", event_id, event_type
        )
        return record

    def audit_log(self) -> list[dict]:
        return list(self._audit)
