"""Batch G — 2 hook companion tool (freeze, investigate)."""

from __future__ import annotations

from pathlib import Path
from typing import List

from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []

_FREEZE_FILE = Path(settings.cache_dir) / ".freeze-dir.txt"
_INVESTIGATE_FILE = Path(settings.cache_dir) / ".investigate-mode.txt"


@mcp_server.tool()
@with_hooks("freeze")
async def freeze(project_dir: str = "") -> str:
    """Freeze mode'u aç: sadece verilen dizin içinde Write/Edit'e izin ver.

    project_dir boşsa freeze kapatılır.
    """
    await tracker.bump("freeze")
    _FREEZE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not project_dir:
        if _FREEZE_FILE.exists():
            _FREEZE_FILE.unlink()
        return "Freeze mode kapatıldı."
    _FREEZE_FILE.write_text(project_dir)
    return f"Freeze aktif: yalnızca {project_dir} altına Write/Edit izinli."


@mcp_server.tool()
@with_hooks("investigate")
async def investigate(topic: str = "") -> str:
    """Investigate mode — kök neden araştırma modu aç. Hook'lar uyarı verir."""
    await tracker.bump("investigate")
    _INVESTIGATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not topic:
        if _INVESTIGATE_FILE.exists():
            _INVESTIGATE_FILE.unlink()
        return "Investigate mode kapatıldı."
    _INVESTIGATE_FILE.write_text(topic)
    return (
        f"Investigate mode aktif — konu: '{topic}'. Hook'lar düzenleme öncesi "
        f"Read/Grep yapılmadıysa uyarı verecek."
    )


REGISTERED_TOOLS.extend(["freeze", "investigate"])
