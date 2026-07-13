# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Performance benchmark MCP tool.

`perf_summary` only reads the JSON left behind by the last benchmark run
(benchmarks/results/*.json) — it never runs a benchmark itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

# REGISTERED_TOOLS must come before app.mcp.server import (017 deviation)
REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


def _benchmarks_dir() -> Path:
    """Repo root / benchmarks / results."""
    return Path(__file__).resolve().parents[4] / "benchmarks" / "results"


def _read_json_safe(path: Path) -> dict:
    if not path.is_file():
        return {"available": False, "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"available": False, "error": str(exc)[:200], "path": str(path)}


@mcp_server.tool()
@with_hooks("perf_summary")
async def perf_summary() -> str:
    """Results of the last benchmark run (cascade, vault, symbol, watchdog)."""
    await tracker.bump("perf_summary")
    base = _benchmarks_dir()
    out = {
        "results_dir": str(base),
        "cascade": _read_json_safe(base / "01_cascade_load.json"),
        "vault": _read_json_safe(base / "02_vault_decrypt_timing.json"),
        "symbol": _read_json_safe(base / "03_symbol_indexing.json"),
        "watchdog": _read_json_safe(base / "04_watchdog_resources.json"),
        "last_run": "2026-04-27",
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(["perf_summary"])
