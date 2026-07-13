# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""system_validate MCP tool.

Wraps `infra/scripts/validate_install.py::validate()` with 5-min cache.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List

# REGISTERED_TOOLS before app.mcp.server import (017 deviation)
REGISTERED_TOOLS: List[str] = []

from app.mcp.middleware import with_hooks  # noqa: E402
from app.mcp.server import mcp_server  # noqa: E402
from app.mcp.tracking import tracker  # noqa: E402


_CACHE: dict = {"data": None, "ts": 0.0}
_CACHE_TTL = 300  # 5 dk


def _load_validator():
    import importlib.util
    import sys

    repo = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location(
        "validate_install", repo / "infra" / "scripts" / "validate_install.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["validate_install"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@mcp_server.tool()
@with_hooks("system_validate")
async def system_validate(force: bool = False) -> str:
    """Run install validation; cached 5 min unless force=True."""
    await tracker.bump("system_validate")
    now = time.time()
    if not force and _CACHE["data"] is not None and now - _CACHE["ts"] < _CACHE_TTL:
        return json.dumps(_CACHE["data"], ensure_ascii=False, indent=2)

    try:
        mod = _load_validator()
        out = mod.validate()
    except Exception as exc:
        out = {"ok": False, "error": str(exc), "results": {}}

    _CACHE["data"] = out
    _CACHE["ts"] = now
    return json.dumps(out, ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(["system_validate"])
