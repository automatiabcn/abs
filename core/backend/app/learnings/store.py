# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Learnings — append-only JSONL store.

Format: {ts, category, lesson, source, project, hash}
Categories: bugfix | delegation | arch | security | perf | ux

The same lesson recorded twice inside the dedup window is skipped (returns None),
so a recurring failure does not bury the store in copies of itself.
Path: data_dir/learnings.jsonl
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


_VALID_CATEGORIES = {"bugfix", "delegation", "arch", "security", "perf", "ux"}
_DEDUP_WINDOW = 86400.0
_LESSON_MAX_LEN = 500


def _path() -> Path:
    p = Path(settings.data_dir) / "learnings.jsonl"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def _hash_lesson(lesson: str) -> str:
    return hashlib.sha256(lesson.encode("utf-8")).hexdigest()[:12]


def log(
    category: str,
    lesson: str,
    *,
    source: str = "manual",
    project: Optional[str] = None,
) -> Optional[str]:
    """Append a learning. Returns None when it is invalid or a recent duplicate."""
    if category not in _VALID_CATEGORIES:
        return None
    lesson = (lesson or "").strip()
    if not lesson:
        return None
    h = _hash_lesson(lesson)
    # The same lesson within the dedup window is not recorded twice — a repeated
    # failure should not flood the store with identical entries.
    now = time.time()
    for entry in recent(limit=50):
        if entry.get("hash") == h and (now - float(entry.get("ts", 0) or 0)) < _DEDUP_WINDOW:
            return None
    entry = {
        "ts": now,
        "category": category,
        "lesson": lesson[:_LESSON_MAX_LEN],
        "source": source,
        "project": project,
        "hash": h,
    }
    try:
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("learnings log fail: %s", exc)
        return None
    return h


def recent(limit: int = 20) -> List[Dict[str, Any]]:
    p = _path()
    if not p.is_file():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()[-limit:]
        out: List[Dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


def recent_count(window_days: int = 30) -> int:
    cutoff = time.time() - window_days * 86400
    return sum(1 for e in recent(limit=2000) if float(e.get("ts", 0) or 0) >= cutoff)


def stats() -> Dict[str, Any]:
    entries = recent(limit=2000)
    by_cat: Dict[str, int] = {}
    for e in entries:
        c = e.get("category", "unknown")
        by_cat[c] = by_cat.get(c, 0) + 1
    return {
        "total": len(entries),
        "by_category": by_cat,
        "last_30d": recent_count(window_days=30),
        "last_7d": recent_count(window_days=7),
    }
