# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Cohere quota threshold pipeline — month-aware, idempotent alarms.

The free Cohere plan allows 1000 calls a month. Each of the 75/90/100% thresholds
fires at most once per calendar month, so a busy month cannot bury the operator
in repeats; the counter resets when the month rolls over.

State (under data_dir):
  cohere_usage.json          — {"month": "YYYY-MM", "count": N}
  cohere_alerts.jsonl        — append-only alert records
  cohere_alerts_seen.json    — {"YYYY-MM": ["warn","danger"]}
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

THRESHOLDS: List[tuple[int, str]] = [
    (100, "limit_hit"),
    (90, "danger"),
    (75, "warn"),
]


def _data_dir() -> Path:
    p = Path(settings.data_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _usage_path() -> Path:
    return _data_dir() / "cohere_usage.json"


def _alerts_path() -> Path:
    return _data_dir() / "cohere_alerts.jsonl"


def _seen_path() -> Path:
    return _data_dir() / "cohere_alerts_seen.json"


def _current_month() -> str:
    return time.strftime("%Y-%m", time.gmtime())


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null") or default
    except Exception:
        return default


def _save_json(path: Path, data: Any) -> None:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _read_usage() -> Dict[str, Any]:
    return _load_json(_usage_path(), {"month": _current_month(), "count": 0})


def _bump_usage(delta: int = 1) -> Dict[str, Any]:
    """Increment the counter; a new calendar month starts from zero."""
    cur = _read_usage()
    month = _current_month()
    if cur.get("month") != month:
        cur = {"month": month, "count": 0}
    cur["count"] = int(cur.get("count") or 0) + max(1, delta)
    _save_json(_usage_path(), cur)
    return cur


def _load_seen() -> Dict[str, List[str]]:
    return _load_json(_seen_path(), {})


def _save_seen(seen: Dict[str, List[str]]) -> None:
    _save_json(_seen_path(), seen)


def _append_alert(level: str, count: int, limit: int, percent: int) -> str:
    alert_id = uuid.uuid4().hex[:12]
    entry = {
        "id": alert_id,
        "ts": time.time(),
        "level": level,
        "count": count,
        "limit": limit,
        "percent": percent,
        "month": _current_month(),
        "ack": False,
        "message": _message_for(level, count, limit, percent),
    }
    p = _alerts_path()
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return alert_id


def _message_for(level: str, count: int, limit: int, percent: int) -> str:
    if level == "limit_hit":
        return f"Cohere monthly limit reached ({count}/{limit}). New calls may be rejected."
    if level == "danger":
        return f"Cohere usage at {percent}% ({count}/{limit}). Calls may be rejected shortly."
    return f"Cohere usage at {percent}% ({count}/{limit}). Line up a fallback provider."


def track_usage(
    count: Optional[int] = None, limit: int = 1000, delta: int = 1
) -> Optional[str]:
    """Record Cohere usage; return the alert level if a threshold just fired.

    Without `count` the internal counter is incremented by `delta`; with `count`
    the caller's absolute figure wins (an authoritative reading from the API).
    """
    if count is not None:
        usage = {"month": _current_month(), "count": int(count)}
        _save_json(_usage_path(), usage)
    else:
        usage = _bump_usage(delta=delta)

    cur = int(usage.get("count") or 0)
    if limit <= 0:
        return None
    percent = int(round(cur / limit * 100))

    seen = _load_seen()
    month = _current_month()
    seen_for_month = list(seen.get(month, []))

    triggered: Optional[str] = None
    # Highest unseen threshold wins — 100% must not be reported as a mere warning.
    for thr, level in THRESHOLDS:
        if percent >= thr and level not in seen_for_month:
            triggered = level
            seen_for_month.append(level)
            break

    if triggered:
        _append_alert(triggered, cur, limit, percent)
        seen[month] = seen_for_month
        _save_seen(seen)
        return triggered
    return None


def read_recent(limit: int = 20) -> List[Dict[str, Any]]:
    p = _alerts_path()
    if not p.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return list(reversed(out))  # newest first


def mark_acknowledged(alert_id: str) -> bool:
    p = _alerts_path()
    if not p.is_file():
        return False
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    found = False
    new_lines: List[str] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:
            new_lines.append(line)
            continue
        if entry.get("id") == alert_id and not entry.get("ack"):
            entry["ack"] = True
            entry["ack_ts"] = time.time()
            found = True
            new_lines.append(json.dumps(entry, ensure_ascii=False))
        else:
            new_lines.append(line)
    if not found:
        return False
    p.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


def unread_count() -> int:
    return sum(1 for a in read_recent(limit=200) if not a.get("ack"))


def usage_snapshot(limit: int = 1000) -> Dict[str, Any]:
    cur = _read_usage()
    count = int(cur.get("count") or 0)
    percent = int(round(count / limit * 100)) if limit else 0
    last_alerts = read_recent(limit=1)
    last = last_alerts[0] if last_alerts else None
    severity = "ok"
    if percent >= 100:
        severity = "limit_hit"
    elif percent >= 90:
        severity = "danger"
    elif percent >= 75:
        severity = "warn"
    return {
        "configured": bool(settings.cohere_api_key),
        "month": cur.get("month"),
        "used_month": count,
        "limit": limit,
        "percent": percent,
        "severity": severity,
        "warning": severity != "ok",
        "last_alert": last,
        "unread_alerts": unread_count(),
    }
