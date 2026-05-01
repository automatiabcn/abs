"""024 Modul A — MCP tool inventory smoke."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path


def _load_smoke():
    repo = Path(__file__).resolve().parents[3]
    p = repo / "infra" / "scripts" / "mcp_tool_smoke.py"
    spec = importlib.util.spec_from_file_location("mcp_tool_smoke", p)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["mcp_tool_smoke"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_smoke_script_exists_and_executable():
    repo = Path(__file__).resolve().parents[3]
    p = repo / "infra" / "scripts" / "mcp_tool_smoke.py"
    assert p.is_file(), f"script missing: {p}"
    text = p.read_text(encoding="utf-8")
    assert "smoke_all" in text
    assert "_SKIP_TOOLS" in text


def test_smoke_run_covers_all_tools():
    mod = _load_smoke()
    out = asyncio.run(mod.smoke_all())
    # 024 baseline 107; later tasks add more (025: status_check, 026: +2)
    assert out["total"] >= 107
    assert out["ok"] + out["skipped"] == out["total"]
    assert out["failed"] == 0


def test_smoke_results_have_expected_keys():
    mod = _load_smoke()
    out = asyncio.run(mod.smoke_all())
    for name, res in out["results"].items():
        assert "ok" in res
        assert "latency_ms" in res
        assert "error" in res
        assert "skip_reason" in res


def test_skip_tools_have_reasons():
    mod = _load_smoke()
    for tool, reason in mod._SKIP_TOOLS.items():
        assert isinstance(reason, str) and len(reason) > 3, f"{tool} skip reason missing"


def test_safe_defaults_have_dict_args():
    mod = _load_smoke()
    for tool, args in mod._SAFE_DEFAULTS.items():
        assert isinstance(args, dict), f"{tool} args must be dict"
