# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Approval Center — DB-backed human-in-the-loop for risky agent actions."""

from app.approvals.service import (
    create_approval_from_result,
    decide_approval,
    get_approval,
    list_approvals,
    log_agent_run,
)

__all__ = [
    "log_agent_run",
    "create_approval_from_result",
    "list_approvals",
    "get_approval",
    "decide_approval",
]
