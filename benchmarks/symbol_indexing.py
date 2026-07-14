"""Symbol graph indexing benchmark (10K LOC sample).

The `core/backend/app` tree is around 10K lines, so this measures a real index time.
Output: benchmarks/results/03_symbol_indexing.json
"""

from __future__ import annotations

import json
import sys
import time
import tracemalloc
from pathlib import Path


def _count_python_loc(root: Path) -> tuple[int, int]:
    files = list(root.rglob("*.py"))
    total_loc = 0
    for p in files:
        try:
            total_loc += sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
        except Exception:
            pass
    return len(files), total_loc


def main() -> dict:
    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo / "core" / "backend"))

    target = repo / "core" / "backend" / "app"
    files, loc = _count_python_loc(target)

    from app.symbols.parser import parse_directory

    tracemalloc.start()
    t0 = time.perf_counter()
    symbols = parse_directory(target)
    elapsed = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "target": str(target),
        "files_count": files,
        "loc_total": loc,
        "symbols_total": len(symbols),
        "elapsed_s": round(elapsed, 3),
        "memory_peak_mb": round(peak / 1024 / 1024, 2),
        "ms_per_file": round((elapsed * 1000) / max(files, 1), 2),
        "expected_threshold_s_for_10k_loc": 60,
    }


if __name__ == "__main__":
    out = main()
    out_path = Path(__file__).resolve().parent / "results" / "03_symbol_indexing.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
