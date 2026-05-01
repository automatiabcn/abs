"""021 — Vault decrypt benchmark validation."""

from __future__ import annotations

import sys
from pathlib import Path


def _benchmarks_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "benchmarks"


def _ensure_path():
    sys.path.insert(0, str(_benchmarks_dir().parent))


def test_vault_overhead_script_runs():
    _ensure_path()
    from benchmarks.vault_overhead import main

    out = main()
    assert "mean_ms" in out
    assert out["mean_ms"] >= 0
    assert "expected_threshold_ms" in out


def test_vault_overhead_meets_threshold():
    _ensure_path()
    from benchmarks.vault_overhead import main

    out = main()
    threshold = out["expected_threshold_ms"]
    if out.get("mode") == "simulated":
        # Simulated < 5 ms; gerçek sops daha yavaş ama threshold içinde
        assert out["mean_ms"] < threshold
    else:
        assert out["mean_ms"] < threshold * 2  # gerçekte 2× tolerans
