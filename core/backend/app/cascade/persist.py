# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""014 — Circuit breaker state persist (restart sonrasi open state korunur)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)


def _state_path() -> Path:
    p = Path(settings.data_dir) / "breaker_state.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def save(states: Dict[str, dict]) -> None:
    """Açık/half-open state'leri persist et. Format: {provider: {state, fail_count, opened_at_real_time}}."""
    payload: Dict[str, Any] = {"saved_at": time.time(), "states": states}
    target = _state_path()
    tmp = target.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(target)
    except OSError as exc:
        logger.warning("breaker persist save fail: %s", exc)


def load() -> Dict[str, dict]:
    p = _state_path()
    if not p.is_file():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        states = d.get("states", {})
        return states if isinstance(states, dict) else {}
    except Exception as exc:
        logger.warning("breaker persist load fail: %s", exc)
        return {}


def cleanup() -> None:
    p = _state_path()
    if p.is_file():
        try:
            p.unlink()
        except OSError:
            pass
