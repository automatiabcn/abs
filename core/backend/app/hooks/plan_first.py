# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Plan-first nudge.

Warns once per task when an active artifact task has passed the action
threshold without a plan.md. Advisory: it never blocks the tool call.
"""

from __future__ import annotations

import os

from .common import (
    allow_once,
    get_active_artifact_task,
    load_rate,
    persist_rate,
    safe_hook,
)

_PLAN_FIRST_THRESHOLD = 3
_RATE_FILE = "plan_first_warned.json"
_WINDOW_SEC = 86400  # one warning per task per day


@safe_hook("plan_first")
def maybe_plan_first_nudge(_tool: str = "", _tool_input: dict | None = None) -> str:
    active = get_active_artifact_task()
    if not active:
        return ""

    task_id = active["task_id"]
    action_count = active["action_count"]
    task_dir = active["task_dir"]

    if action_count < _PLAN_FIRST_THRESHOLD:
        return ""

    plan_path = os.path.join(task_dir, "plan.md")
    if os.path.exists(plan_path):
        return ""

    rate = load_rate(_RATE_FILE)
    if not allow_once(rate, task_id, _WINDOW_SEC):
        return ""
    persist_rate(_RATE_FILE, rate)

    return (
        f"PLAN-FIRST WARNING: this task ({task_id}) has reached {action_count} file "
        f"changes with no plan.md. Consider adding one at {task_dir}/plan.md — "
        f"planning before coding cuts rework on multi-file tasks. "
        f"This warning will not repeat for this task."
    )
