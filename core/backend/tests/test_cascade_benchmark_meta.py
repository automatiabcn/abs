"""Cascade load benchmark scenario metadata."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _benchmarks_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "benchmarks"


def test_cascade_load_script_exists_and_imports():
    p = _benchmarks_dir() / "cascade_load.py"
    assert p.is_file()
    sys.path.insert(0, str(_benchmarks_dir().parent))
    from benchmarks.cascade_load import _scenario_summary

    summary = _scenario_summary()
    assert summary["users"] == 100
    assert summary["spawn_rate"] == 10
    assert summary["endpoint"] == "/v1/cascade/ask"
    assert summary["expected_p99_ms"] == 1000


def test_cascade_load_evidence_json_valid():
    p = _benchmarks_dir() / "results" / "01_cascade_load.json"
    if not p.is_file():
        # Optional before first CI run — only script syntax check
        return
    data = json.loads(p.read_text())
    assert "name" in data or "scenario" in data or "users" in data
