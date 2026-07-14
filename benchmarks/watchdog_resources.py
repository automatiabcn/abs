"""Watchdog process resource sample (psutil RSS + CPU).

Spec: a 10-minute sample, every 10s. Shorter in CI: 60s, every 5s.
Output: benchmarks/results/04_watchdog_resources.json
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]


def main(duration_s: int = 60, interval_s: int = 5) -> dict:
    if psutil is None:
        return {
            "error": "psutil not installed",
            "samples": [],
        }

    pid = os.getpid()
    proc = psutil.Process(pid)
    proc.cpu_percent(interval=None)  # warmup

    samples: list[dict] = []
    started = time.time()
    while time.time() - started < duration_s:
        try:
            mem = proc.memory_info()
            samples.append(
                {
                    "t_offset_s": round(time.time() - started, 2),
                    "rss_mb": round(mem.rss / 1024 / 1024, 2),
                    "vms_mb": round(mem.vms / 1024 / 1024, 2),
                    "cpu_percent": proc.cpu_percent(interval=None),
                    "num_threads": proc.num_threads(),
                    "open_fds": proc.num_fds() if hasattr(proc, "num_fds") else None,
                }
            )
        except Exception as exc:
            samples.append({"t_offset_s": round(time.time() - started, 2), "error": str(exc)})
        time.sleep(interval_s)

    rss_values = [s["rss_mb"] for s in samples if "rss_mb" in s]
    cpu_values = [s["cpu_percent"] for s in samples if "cpu_percent" in s]
    return {
        "duration_s": duration_s,
        "interval_s": interval_s,
        "sample_count": len(samples),
        "rss_mb_mean": round(sum(rss_values) / max(len(rss_values), 1), 2),
        "rss_mb_max": round(max(rss_values, default=0), 2),
        "cpu_percent_mean": round(sum(cpu_values) / max(len(cpu_values), 1), 2),
        "cpu_percent_max": round(max(cpu_values, default=0), 2),
        "expected_rss_mb_threshold": 200,
        "expected_cpu_pct_threshold": 5,
        "samples": samples,
    }


if __name__ == "__main__":
    out = main(duration_s=20, interval_s=4)  # quick run for evidence
    out_path = Path(__file__).resolve().parent / "results" / "04_watchdog_resources.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
