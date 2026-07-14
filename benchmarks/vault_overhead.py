"""Vault decrypt overhead benchmark (sops + age timing).

Measures a real decrypt when the sops binary is installed, and simulates one otherwise.
Output: benchmarks/results/02_vault_decrypt_timing.json
"""

from __future__ import annotations

import json
import shutil
import statistics
import time
from pathlib import Path


def _sops_available() -> bool:
    return shutil.which("sops") is not None and shutil.which("age") is not None


def _measure_decrypt_simulated(iterations: int = 50) -> dict:
    """Stand in for an encrypted read when sops + age are absent (file hash + base64 decode)."""
    import base64
    import hashlib

    payload = base64.b64encode(b"x" * 4096).decode()
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        for _i in range(5):  # repeat for a stable timing
            digest = hashlib.sha256(payload.encode()).hexdigest()
            _ = base64.b64decode(payload)
            _ = digest[:16]
        times.append((time.perf_counter() - t0) * 1000)
    return {
        "mode": "simulated",
        "iterations": iterations,
        "mean_ms": round(statistics.mean(times), 3),
        "median_ms": round(statistics.median(times), 3),
        "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 3),
        "max_ms": round(max(times), 3),
        "expected_threshold_ms": 50,
    }


def _measure_decrypt_real(secrets_path: Path, iterations: int = 5) -> dict:
    import subprocess

    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        subprocess.run(
            ["sops", "--decrypt", str(secrets_path)],
            check=True,
            capture_output=True,
            timeout=10,
        )
        times.append((time.perf_counter() - t0) * 1000)
    return {
        "mode": "real_sops",
        "secrets_path": str(secrets_path),
        "iterations": iterations,
        "mean_ms": round(statistics.mean(times), 3),
        "median_ms": round(statistics.median(times), 3),
        "max_ms": round(max(times), 3),
        "expected_threshold_ms": 100,
    }


def main() -> dict:
    if _sops_available():
        candidate = Path.cwd() / "infra" / "secrets.enc.json"
        if candidate.is_file():
            return _measure_decrypt_real(candidate)
    return _measure_decrypt_simulated()


if __name__ == "__main__":
    out = main()
    out_path = Path(__file__).resolve().parent / "results" / "02_vault_decrypt_timing.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
