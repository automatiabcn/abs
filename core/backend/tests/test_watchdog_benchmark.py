"""021 — Watchdog psutil sampler validation."""

from __future__ import annotations

import sys
from pathlib import Path


def _benchmarks_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "benchmarks"


def _ensure_path():
    sys.path.insert(0, str(_benchmarks_dir().parent))


def test_watchdog_sampler_runs_short():
    _ensure_path()
    from benchmarks.watchdog_resources import main

    out = main(duration_s=2, interval_s=1)  # quick smoke test
    assert "samples" in out
    assert out["sample_count"] >= 1
    if "rss_mb_mean" in out and out["rss_mb_mean"] > 0:
        # RSS değeri makul aralıkta — Python process en az birkaç MB
        assert out["rss_mb_mean"] >= 1
        assert out["rss_mb_mean"] < 2000
