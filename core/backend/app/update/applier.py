# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Update apply trigger.

A backend container cannot restart itself. `trigger_pull()` only writes an
`update_pending.json` flag to the host volume; a host-side cron job or systemd
unit picks it up and runs `docker compose pull && docker compose up -d`.

This is deliberate, and is written down in `summary.md` and `docs/operations.md`.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Dict

from app.config import settings

logger = logging.getLogger(__name__)


def _flag_path() -> Path:
    p = Path(settings.data_dir) / "update_pending.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def docker_available() -> bool:
    return shutil.which("docker") is not None


async def trigger_pull() -> Dict:
    """Host volume'una pending flag yaz. Container icinde docker pull CALISTIRMAZ."""
    flag = _flag_path()
    payload = {"requested_at": time.time(), "status": "pending"}
    flag.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def pending_status() -> Dict:
    flag = _flag_path()
    if not flag.is_file():
        return {"status": "none"}
    try:
        return json.loads(flag.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "corrupt"}


def clear_pending() -> bool:
    flag = _flag_path()
    if flag.is_file():
        try:
            flag.unlink()
            return True
        except OSError:
            return False
    return False
