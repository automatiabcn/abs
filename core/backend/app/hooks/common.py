# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Shared hook helpers — rate-limit file I/O, logging, freeze-path checks.

Pure functions. Every file they touch lives under `settings.cache_dir`; nothing
is hardcoded to a temp directory.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)

# Repo housekeeping files stay writable even when a freeze path is active.
ALWAYS_ALLOW_FILES = frozenset(
    {
        ".gitignore",
        ".gitattributes",
        ".gitkeep",
        "LICENSE",
        "LICENSE.md",
        "LICENSE.txt",
    }
)

# Subagent types that may be delegated to.
ALLOWED_AGENT_TYPES = frozenset(
    {
        "general-purpose",
        "Explore",
        "code-reviewer",
        "docs-writer",
        "quality-writer",
        "translator",
    }
)


def cache_path(filename: str) -> Path:
    """Path under `settings.cache_dir`, with parents created."""
    p = Path(settings.cache_dir) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_rate(filename: str) -> Dict[str, float]:
    """Load the rate-limit state; a missing or corrupt file reads as empty."""
    p = cache_path(filename)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def persist_rate(
    filename: str, rate: Dict[str, float], prune_older_than: float = 86400
) -> None:
    """Persist the rate state, dropping keys older than the prune window so the
    file cannot grow without bound."""
    p = cache_path(filename)
    try:
        cutoff = time.time() - prune_older_than
        pruned = {k: v for k, v in rate.items() if v > cutoff}
        p.write_text(json.dumps(pruned), encoding="utf-8")
    except Exception as exc:
        logger.info("rate persist failed %s: %s", filename, exc)


def allow_once(rate: Dict[str, float], key: str, window_sec: float) -> bool:
    """True if `key` has not fired within `window_sec`; records the hit."""
    now = time.time()
    last = rate.get(key, 0)
    if now - last < window_sec:
        return False
    rate[key] = now
    return True


def deny(reason: str, *, permission_decision: str = "deny") -> Dict[str, Any]:
    """PreToolUse hook payload that blocks the tool call."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecisionReason": reason,
            "permissionDecision": permission_decision,
        }
    }


def additional_context(text: str) -> Dict[str, Any]:
    """PreToolUse hook payload that adds context but still allows the call."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": text,
        }
    }


def safe_hook(name: str):
    """Decorator: a raising hook logs and returns "" instead of propagating."""

    def _wrap(fn):
        def _call(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # isolation — one hook must not kill the rest
                logger.info("hook %s failed: %s", name, exc)
                return ""

        _call.__name__ = fn.__name__
        return _call

    return _wrap


def get_active_artifact_task() -> Dict[str, Any] | None:
    """The active artifact task, or None. "Active" is the most recently modified
    directory under `settings.artifacts_dir` — there is no explicit marker."""
    base = Path(settings.artifacts_dir)
    if not base.is_dir():
        return None
    try:
        subdirs = [d for d in base.iterdir() if d.is_dir()]
        if not subdirs:
            return None
        active = max(subdirs, key=lambda d: d.stat().st_mtime)
        # Prefer the counter file; fall back to counting files in the task dir.
        count_file = active / "action_count.txt"
        if count_file.is_file():
            try:
                action_count = int(count_file.read_text().strip() or "0")
            except ValueError:
                action_count = 0
        else:
            action_count = sum(1 for _ in active.iterdir() if _.is_file())
        return {
            "task_id": active.name,
            "task_dir": str(active),
            "action_count": action_count,
        }
    except Exception as exc:
        logger.info("artifact lookup failed: %s", exc)
        return None


def bump_action_count(task_dir: str) -> int:
    """Increment the task action counter and return the new value."""
    p = Path(task_dir) / "action_count.txt"
    try:
        current = 0
        if p.is_file():
            current = int(p.read_text().strip() or "0")
        p.write_text(str(current + 1))
        return current + 1
    except Exception:
        return 0
