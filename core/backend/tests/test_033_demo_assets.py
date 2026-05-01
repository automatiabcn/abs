"""033 Modul J + K + L — screenshot generator + video script + demo MCP tool."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCREENSHOT_SCRIPT = REPO / "infra" / "scripts" / "generate_demo_screenshots.py"
VIDEO_SCRIPT = REPO / "docs" / "demo" / "video-script.md"


# ---------- J: screenshot generator script ----------


def test_screenshot_script_is_importable_and_defines_screens():
    spec = importlib.util.spec_from_file_location(
        "generate_demo_screenshots", SCREENSHOT_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    assert hasattr(mod, "SCREENS")
    assert hasattr(mod, "VIEWPORTS")
    assert len(mod.SCREENS) >= 8, "expected at least 8 screen entries"
    assert set(mod.VIEWPORTS.keys()) == {"desktop", "mobile"}
    assert hasattr(mod, "run") and callable(mod.run)


# ---------- K: video script ----------


def test_video_script_present_and_long_enough():
    assert VIDEO_SCRIPT.exists(), f"missing video script at {VIDEO_SCRIPT}"
    body = VIDEO_SCRIPT.read_text(encoding="utf-8")
    assert len(body.split()) >= 400, "video script too short"
    lower = body.lower()
    for kw in ("0:00", "5:00", "loom"):
        assert kw in lower, f"missing keyword: {kw}"


# ---------- L: demo_readiness_status MCP ----------


def test_demo_readiness_status_payload_shape():
    from app.mcp.tools.demo_tools import demo_readiness_status

    raw = asyncio.run(demo_readiness_status())
    out = json.loads(raw)
    for key in (
        "demo_mode",
        "mock_providers",
        "seed_version",
        "seed_script_present",
        "video_script_present",
        "screenshots",
    ):
        assert key in out
    assert out["seed_script_present"] is True
    assert out["video_script_present"] is True


def test_demo_readiness_status_registered_in_server():
    from app.mcp.server import mcp_server

    tools = asyncio.run(mcp_server.list_tools())
    names = {t.name for t in tools}
    assert "demo_readiness_status" in names
