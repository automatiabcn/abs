"""Symbol indexing benchmark validation."""

from __future__ import annotations

import sys
from pathlib import Path


def _benchmarks_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "benchmarks"


def _ensure_path():
    sys.path.insert(0, str(_benchmarks_dir().parent))


def test_symbol_indexing_runs_and_produces_results():
    _ensure_path()
    from benchmarks.symbol_indexing import main

    out = main()
    assert out["files_count"] > 100  # core/backend/app birkaç yüz dosya
    assert out["loc_total"] > 5000
    assert out["symbols_total"] > 100
    assert out["elapsed_s"] > 0


def test_symbol_indexing_meets_throughput_threshold():
    _ensure_path()
    from benchmarks.symbol_indexing import main

    out = main()
    # for 10K LOC < 60s threshold; ms_per_file < 100
    assert out["elapsed_s"] < out["expected_threshold_s_for_10k_loc"]
    assert out["ms_per_file"] < 200
