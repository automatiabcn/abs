# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""`demo_status` MCP tool.

Reports whether demo mode is on, seed version, mock-provider state,
known screenshot paths and demo-video script path.

NOTE: an existing 011 `demo_status` tool already exists in license_tools.py
that reports trial-license demo state. We register THIS new tool under the
different name `demo_readiness_status` to avoid clobbering it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

REGISTERED_TOOLS: List[str] = []

from app.config import settings  # noqa: E402
from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402

try:
    REPO_ROOT = Path(__file__).resolve().parents[5]
except IndexError:
    # Container layout differs from monorepo — fall back to env or /app.
    import os as _os

    REPO_ROOT = Path(_os.environ.get("ABS_REPO_ROOT", "/app"))
SCREENSHOT_DIR = REPO_ROOT / "docs" / "demo" / "screenshots"
VIDEO_SCRIPT = REPO_ROOT / "docs" / "demo" / "video-script.md"
SEED_SCRIPT = REPO_ROOT / "infra" / "scripts" / "seed_demo_data.py"


def _list_screenshots() -> list[str]:
    if not SCREENSHOT_DIR.exists():
        return []
    return sorted(p.name for p in SCREENSHOT_DIR.glob("*.png"))


@mcp_server.tool()
@with_hooks("demo_readiness_status")
async def demo_readiness_status() -> str:
    """Demo readiness snapshot (demo mode flag, seed version, assets)."""
    await tracker.bump("demo_readiness_status")
    payload = {
        "demo_mode": bool(settings.demo_mode),
        "mock_providers": bool(settings.provider_mock),
        "seed_version": settings.demo_seed_version,
        "seed_script_present": SEED_SCRIPT.exists(),
        "video_script_present": VIDEO_SCRIPT.exists(),
        "screenshots": _list_screenshots(),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


REGISTERED_TOOLS.extend(["demo_readiness_status"])
