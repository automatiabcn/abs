"""GUARD 7 — Plan-First Mode.

Aktif artifact task varsa ve action_count >= threshold ama plan.md yoksa
bir uyarı string'i döner. Task başına sadece 1 uyarı (rate-limit).
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
_WINDOW_SEC = 86400  # 24 saat — task başına 1 uyarı


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

    # plan.md varsa uyarma
    plan_path = os.path.join(task_dir, "plan.md")
    if os.path.exists(plan_path):
        return ""

    rate = load_rate(_RATE_FILE)
    if not allow_once(rate, task_id, _WINDOW_SEC):
        return ""
    persist_rate(_RATE_FILE, rate)

    return (
        f"PLAN-FIRST UYARI: Bu görev ({task_id}) {action_count} dosya değişikliğine "
        f"ulaştı ama plan.md yok. Öneri: artifact dizinine plan.md ekle "
        f"({task_dir}/plan.md). 'Plan önce, kod sonra' prensibi çok dosyalı "
        f"görevlerde rework'ü azaltır. Bu uyarı bu task için bir daha gelmeyecek."
    )
