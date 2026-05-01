"""030 Modul H — `mcp_tool_smoke` script accepts the 6 new 030 tools."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "infra"
    / "scripts"
    / "mcp_tool_smoke.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("mcp_tool_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_new_030_tools_in_skip_or_safe_defaults():
    mod = _load_module()
    skip = getattr(mod, "_SKIP_TOOLS")
    safe = getattr(mod, "_SAFE_DEFAULTS")
    new_tools = {
        "ask_compound",
        "ask_compound_mini",
        "ask_cerebras_qwen",
        "ask_gemini_latest",
        "ask_gemini_pro_latest",
        "news_digest",
    }
    for name in new_tools:
        assert (
            name in skip or name in safe
        ), f"{name} missing from both _SKIP_TOOLS and _SAFE_DEFAULTS"
