# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Companions to the hooks: the tools that arm and disarm freeze and investigate
mode. The hooks read the state files these write."""

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
    """Arm freeze mode: Write/Edit is allowed only under project_dir.

    An empty project_dir disarms it.
    """
    await tracker.bump("freeze")
    _FREEZE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not project_dir:
        if _FREEZE_FILE.exists():
            _FREEZE_FILE.unlink()
        return "Freeze mode off."
    _FREEZE_FILE.write_text(project_dir)
    return f"Freeze on: Write/Edit allowed only under {project_dir}."


@mcp_server.tool()
@with_hooks("investigate")
async def investigate(topic: str = "") -> str:
    """Arm investigate mode: hooks warn on an edit that was not preceded by
    reading the code. An empty topic disarms it."""
    await tracker.bump("investigate")
    _INVESTIGATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not topic:
        if _INVESTIGATE_FILE.exists():
            _INVESTIGATE_FILE.unlink()
        return "Investigate mode off."
    _INVESTIGATE_FILE.write_text(topic)
    return (
        f"Investigate mode on — topic: '{topic}'. Hooks will warn about an edit "
        f"made without reading or searching the code first."
    )


REGISTERED_TOOLS.extend(["freeze", "investigate"])
