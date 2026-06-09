# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Agentic Growth — Agent Registry + Agent Runtime.

The agentic core of the product: a registry of purpose-scoped agents (each with
its allowed tools, data sources, model, risk level and approval rules) and a
runtime that executes one against a task, building context from RAG + the Growth
Context Graph, calling the Model Gateway, and emitting a structured result whose
risky actions route to the Approval Center.

Agents NEVER touch connectors / DB / MCP directly — access flows through the
runtime's context builder + Tool Gateway, exactly as the design doc requires.
"""

from app.agents.registry import AGENTS, Agent, agents_by_category, get_agent

__all__ = ["AGENTS", "Agent", "get_agent", "agents_by_category"]
