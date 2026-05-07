# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""011 — Demo mode: kurulumdan sonra 14 gün full feature.

Demo state file: {data_dir}/demo_state.json
  {"started_at": <unix ts>, "expires_at": <unix ts>, "duration_days": 14}

Lisans set edilince (`settings.license_key`) demo bypass — `is_active()` False döner.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Optional

from app.config import settings

DEMO_DURATION_DAYS = 14


def _state_path() -> Path:
    p = Path(settings.data_dir) / "demo_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_state() -> Optional[Dict]:
    p = _state_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "started_at" in data and "expires_at" in data:
            return data
    except Exception:
        return None
    return None


def start_demo() -> Dict:
    """Demo zaten başlatılmadıysa başlat. Idempotent — mevcut state aynen döner."""
    existing = _read_state()
    if existing:
        return existing
    now = time.time()
    state = {
        "started_at": now,
        "expires_at": now + DEMO_DURATION_DAYS * 86400,
        "duration_days": DEMO_DURATION_DAYS,
    }
    _state_path().write_text(json.dumps(state), encoding="utf-8")
    return state


def status() -> Dict:
    """Demo durum snapshot — UI ve gate ortak feed."""
    state = _read_state()
    if not state:
        return {
            "started": False,
            "active": False,
            "expired": False,
            "days_remaining": None,
            "started_at": None,
            "expires_at": None,
        }
    now = time.time()
    expires_at = float(state["expires_at"])
    expired = now >= expires_at
    days_remaining = max(0, int((expires_at - now) / 86400))
    return {
        "started": True,
        "active": not expired,
        "expired": expired,
        "days_remaining": days_remaining,
        "started_at": state.get("started_at"),
        "expires_at": expires_at,
    }


def is_active() -> bool:
    """Lisans yoksa demo aktif mi?"""
    if settings.license_key:
        return False
    return status()["active"]


def reset() -> None:
    """Demo state sil — ilk kurulum reset (test/dev)."""
    p = _state_path()
    if p.is_file():
        try:
            p.unlink()
        except Exception:
            pass
