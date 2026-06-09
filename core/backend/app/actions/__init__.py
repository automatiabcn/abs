# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Action layer — execute an approved agent action (Stage E)."""

from app.actions.executor import execute_for_approval, list_actions

__all__ = ["execute_for_approval", "list_actions"]
