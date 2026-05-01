"""Hook ortak yardımcılar — rate-limit dosya I/O, logger, freeze path kontrolü.

SERVER guard_logic.py'den yeniden paketlenen saf fonksiyonlar. Tüm dosya
yolları `settings.cache_dir` altına alınır; hardcoded `/tmp/abs_*` yok.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)

# `.gitignore`, `.gitattributes` gibi özel dosyalar — Write/Edit'te freeze check bypass
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

# Subagent tipleri: delege izin verilen agent isimleri
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
    """`settings.cache_dir` altına file path."""
    p = Path(settings.cache_dir) / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_rate(filename: str) -> Dict[str, float]:
    """Rate-limit JSON dosyasını yükle (yoksa boş dict)."""
    p = cache_path(filename)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def persist_rate(filename: str, rate: Dict[str, float], prune_older_than: float = 86400) -> None:
    """Rate dict'ini kaydet. 24 saatten eski key'leri temizle."""
    p = cache_path(filename)
    try:
        cutoff = time.time() - prune_older_than
        pruned = {k: v for k, v in rate.items() if v > cutoff}
        p.write_text(json.dumps(pruned), encoding="utf-8")
    except Exception as exc:
        logger.info("rate persist failed %s: %s", filename, exc)


def allow_once(rate: Dict[str, float], key: str, window_sec: float) -> bool:
    """Key için `window_sec` içinde daha önce tetiklenmediyse True döndür + kaydet."""
    now = time.time()
    last = rate.get(key, 0)
    if now - last < window_sec:
        return False
    rate[key] = now
    return True


def deny(reason: str, *, permission_decision: str = "deny") -> Dict[str, Any]:
    """Claude Code PreToolUse hook spec — tool call'ı engelle."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecisionReason": reason,
            "permissionDecision": permission_decision,
        }
    }


def additional_context(text: str) -> Dict[str, Any]:
    """Claude Code PreToolUse hook spec — ek context ekle (izin vermeye devam)."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": text,
        }
    }


def safe_hook(name: str):
    """Decorator: hook fonksiyonu hata atsa bile sessiz log + boş string döndür."""

    def _wrap(fn):
        def _call(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # hook izolasyonu — bir hook diğerini kesmez
                logger.info("hook %s failed: %s", name, exc)
                return ""

        _call.__name__ = fn.__name__
        return _call

    return _wrap


def get_active_artifact_task() -> Dict[str, Any] | None:
    """Aktif artifact task (plan_first için). `settings.artifacts_dir` altındaki en
    yeni klasörü baz alır; yoksa None. MVP: basit mtime-based tespit."""
    base = Path(settings.artifacts_dir)
    if not base.is_dir():
        return None
    try:
        subdirs = [d for d in base.iterdir() if d.is_dir()]
        if not subdirs:
            return None
        active = max(subdirs, key=lambda d: d.stat().st_mtime)
        # action_count dosyasından oku; yoksa dosya sayısı
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
    """Task action sayacını +1."""
    p = Path(task_dir) / "action_count.txt"
    try:
        current = 0
        if p.is_file():
            current = int(p.read_text().strip() or "0")
        p.write_text(str(current + 1))
        return current + 1
    except Exception:
        return 0
