# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""016 — Symbol indexing orchestrator."""

from __future__ import annotations

from typing import Any, Dict

from ._safe_path import safe_resolve
from .parser import parse_directory
from .store import bulk_insert, reset, stats as store_stats


def index_path(path: str, replace: bool = False) -> Dict[str, Any]:
    try:
        p = safe_resolve(path)
    except PermissionError:
        return {"error": "path outside allowed roots", "indexed": 0}
    if not p.exists():
        return {"error": f"yol yok: {path}", "indexed": 0}
    if replace:
        reset()
    syms = parse_directory(p)
    inserted = bulk_insert(syms)
    return {"path": str(p), "indexed": inserted, "stats": store_stats()}
