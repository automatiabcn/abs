"""Watchdog Discord/email alert (skeleton).

WATCHDOG_DISCORD_WEBHOOK reads from env. Returns False if missing — does not raise exception.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


async def send_discord_alert(message: str) -> bool:
    webhook = os.environ.get("WATCHDOG_DISCORD_WEBHOOK", "")
    if not webhook:
        logger.info("[watchdog] no DISCORD_WEBHOOK set — skipping alert")
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(webhook, json={"content": message})
        return r.status_code < 400
    except Exception as exc:
        logger.warning("[watchdog] discord alert failed: %s", exc)
        return False
