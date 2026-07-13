# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Agentic workflows — run a sequence of agents, threading context + approvals.

Distinct from the classic `workflow_v10` (integration/sync). This is the
agentic path: trigger → agent → agent → … where each step is an Agent Runtime
execution and risky steps open Approval Center items (Workflow Designer screen).
"""

from app.agentic_workflows.service import (
    get_definition,
    list_runs,
    ordered_agent_steps,
    palette,
    run_workflow,
    run_workflow_graph,
    save_definition,
)

__all__ = [
    "run_workflow",
    "run_workflow_graph",
    "list_runs",
    "palette",
    "get_definition",
    "save_definition",
    "ordered_agent_steps",
]
