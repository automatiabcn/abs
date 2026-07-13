# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Aggregation and drift signal over the judge log."""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from .log import read_recent


def _avg(values: List[float]) -> Optional[float]:
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def aggregate(window_days: int = 7) -> Dict[str, Any]:
    """Summarize the judgments of the last `window_days` days and derive a
    drift signal by comparing them with the window before that."""
    cutoff = time.time() - window_days * 86400
    cutoff_prev = cutoff - window_days * 86400

    # Read a slice wide enough to cover both windows.
    entries = read_recent(limit=1000)

    cur_window = [e for e in entries if (e.get("ts") or 0) >= cutoff]
    prev_window = [e for e in entries if cutoff_prev <= (e.get("ts") or 0) < cutoff]

    avg_combined = _avg([e.get("combined_score") for e in cur_window])
    avg_ast = _avg([e.get("ast_score") for e in cur_window])
    avg_llm = _avg([e.get("llm_score") for e in cur_window])
    prev_avg = _avg([e.get("combined_score") for e in prev_window])

    drift_signal = "stable"
    if avg_combined is not None and prev_avg is not None:
        diff = avg_combined - prev_avg
        if diff <= -0.5:
            # Scores falling: either the bar rose or the code got worse.
            drift_signal = "tightening"
        elif diff >= 0.5:
            drift_signal = "loosening"

    outcome_counts: Dict[str, int] = Counter()
    for e in cur_window:
        outcome_counts[e.get("outcome") or "null"] += 1

    files: Dict[str, List[float]] = defaultdict(list)
    for e in cur_window:
        f = e.get("file")
        s = e.get("combined_score")
        if f and isinstance(s, (int, float)):
            files[f].append(float(s))
    top_files = [
        {"file": f, "avg_score": round(sum(v) / len(v), 2), "n": len(v)}
        for f, v in sorted(files.items(), key=lambda kv: -len(kv[1]))[:5]
    ]

    return {
        "window_days": window_days,
        "count": len(cur_window),
        "avg_combined": avg_combined,
        "avg_ast": avg_ast,
        "avg_llm": avg_llm,
        "prev_avg_combined": prev_avg,
        "drift_signal": drift_signal,
        "outcome_counts": dict(outcome_counts),
        "top_files": top_files,
    }


def recent(limit: int = 20) -> List[Dict[str, Any]]:
    return read_recent(limit=limit)
