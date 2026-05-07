# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""010 — Judge persona live training (deterministik drift-tabanlı adapt).

Algoritma:
  1. judge_log.jsonl son N entry oku (default 200).
  2. accept/reject outcome'lu entry'lerin persona_drift ortalaması.
  3. reject_avg > accept_avg + 0.10 → threshold gevşet (loosen).
  4. accept_avg < reject_avg - 0.10 → threshold sertleş (tighten).
  5. Aralık: docstring [0.30, 0.85], type_hints [0.40, 0.95].
  6. cache_dir/persona.json atomic temp+rename.
  7. cache_dir/persona_history.jsonl audit append.

Idempotent: aynı log girdileriyle 2. çağrı 'stable' döner.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings
from app.judge.persona import DEFAULT_PERSONA, load_persona


_ADJUST_STEP = 0.05
_DELTA_THRESHOLD = 0.10
_DOCSTRING_RANGE = (0.30, 0.85)
_TYPE_HINTS_RANGE = (0.40, 0.95)


def _persona_path() -> Path:
    p = Path(settings.cache_dir) / "persona.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _history_path() -> Path:
    p = Path(settings.cache_dir) / "persona_history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _judge_log_path() -> Path:
    return Path(settings.data_dir) / "judge_log.jsonl"


def _read_log_entries(limit: int) -> list[Dict[str, Any]]:
    p = _judge_log_path()
    if not p.is_file():
        return []
    out: list[Dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _avg_drift(entries: list[Dict[str, Any]], outcome: str) -> Optional[float]:
    drifts = [
        float(e["persona_drift"])
        for e in entries
        if e.get("outcome") == outcome and isinstance(e.get("persona_drift"), (int, float))
    ]
    if not drifts:
        return None
    return round(sum(drifts) / len(drifts), 4)


def _clamp(value: float, lo: float, hi: float) -> float:
    return round(max(lo, min(hi, value)), 4)


def _atomic_write_persona(persona: Dict[str, float]) -> None:
    target = _persona_path()
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(persona, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)


def _append_history(record: Dict[str, Any]) -> None:
    with open(_history_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def train_persona(min_samples: int = 10, history_limit: int = 200) -> Dict[str, Any]:
    """Live training — outcome'lara göre persona threshold'larını adapt et."""
    entries = _read_log_entries(history_limit)
    samples_with_outcome = [e for e in entries if e.get("outcome") in ("accept", "reject")]
    sample_size = len(samples_with_outcome)

    before = load_persona()

    if sample_size < min_samples:
        return {
            "action": "insufficient_data",
            "samples": sample_size,
            "min_samples": min_samples,
            "accept_drift_avg": None,
            "reject_drift_avg": None,
            "before": before,
            "after": before,
        }

    accept_avg = _avg_drift(samples_with_outcome, "accept")
    reject_avg = _avg_drift(samples_with_outcome, "reject")

    after = dict(before)
    action = "stable"
    if accept_avg is not None and reject_avg is not None:
        delta = reject_avg - accept_avg
        if delta > _DELTA_THRESHOLD:
            after["docstring_ratio"] = _clamp(
                before["docstring_ratio"] - _ADJUST_STEP, *_DOCSTRING_RANGE
            )
            after["type_hints_ratio"] = _clamp(
                before["type_hints_ratio"] - _ADJUST_STEP, *_TYPE_HINTS_RANGE
            )
            action = "loosen"
        elif delta < -_DELTA_THRESHOLD:
            after["docstring_ratio"] = _clamp(
                before["docstring_ratio"] + _ADJUST_STEP, *_DOCSTRING_RANGE
            )
            after["type_hints_ratio"] = _clamp(
                before["type_hints_ratio"] + _ADJUST_STEP, *_TYPE_HINTS_RANGE
            )
            action = "tighten"

    if after != before:
        _atomic_write_persona(after)

    record = {
        "ts": time.time(),
        "action": action,
        "samples": sample_size,
        "accept_drift_avg": accept_avg,
        "reject_drift_avg": reject_avg,
        "before": before,
        "after": after,
    }
    _append_history(record)
    return record


def persona_status() -> Dict[str, Any]:
    """Mevcut persona + son training tarihi + history özeti."""
    persona = load_persona()
    history_size = 0
    last_action: Optional[Dict[str, Any]] = None
    p = _history_path()
    if p.is_file():
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
            history_size = len(lines)
            if lines:
                last_action = json.loads(lines[-1])
        except Exception:
            pass
    return {
        "persona": persona,
        "is_default": persona == DEFAULT_PERSONA,
        "history_size": history_size,
        "last_training": last_action,
    }


def reset_persona() -> Dict[str, Any]:
    """persona.json sil → DEFAULT_PERSONA'ya dön. history korunur."""
    path = _persona_path()
    removed = False
    if path.is_file():
        try:
            path.unlink()
            removed = True
        except Exception:
            pass
    return {
        "action": "reset",
        "removed_file": removed,
        "persona": dict(DEFAULT_PERSONA),
    }
