# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""ABS NL → workflow builder package."""

from .ontology import (
    Edge,
    EdgeKind,
    Node,
    NodeConfig,
    NodeKind,
    Trigger,
    TriggerKind,
    Variable,
    VariableScope,
    Workflow,
    WorkflowTemplate,
    build_simple_chain,
)

__all__ = [
    "Edge",
    "EdgeKind",
    "Node",
    "NodeConfig",
    "NodeKind",
    "Trigger",
    "TriggerKind",
    "Variable",
    "VariableScope",
    "Workflow",
    "WorkflowTemplate",
    "build_simple_chain",
]
