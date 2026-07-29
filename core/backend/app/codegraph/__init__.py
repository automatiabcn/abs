# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Deterministic directed call-graph: blast-radius, callers, callees.

Reuses app.symbols.parser for extraction and adds a directed edge layer with
name resolution + reverse-BFS — the "what breaks if I change X?" answer no
vector index can give. LLM-free, offline, per-workspace/tenant SQLite.
"""

from .graph import (
    blast_radius,
    build,
    callees,
    callers,
    graph_related,
    stats,
    workspace_key,
)

__all__ = [
    "build",
    "blast_radius",
    "callers",
    "callees",
    "graph_related",
    "stats",
    "workspace_key",
]
