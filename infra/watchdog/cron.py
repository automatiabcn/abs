"""Watchdog cron entry point (skeleton).

Hetzner VPS cron:
  0 6 * * *  cd /opt/abs-watchdog && .venv/bin/python -m watchdog.cron
"""

from __future__ import annotations

import asyncio
import json

from .alerter import send_discord_alert
from .scanner import scan_all


async def main() -> None:
    results = scan_all()
    print(json.dumps(results, indent=2, ensure_ascii=False))
    # 015 — diff/alert: compare with previous snapshot + send to Discord if changes
    # Temporary stub notification (only if webhook is defined)
    await send_discord_alert(f"watchdog scan: {len(results)} provider taranmıştır")


if __name__ == "__main__":
    asyncio.run(main())
