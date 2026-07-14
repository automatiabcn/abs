"""Annual billing SKU bootstrap."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "infra"
        / "scripts"
        / "setup_stripe_products.py"
    )


def _run(args, env_extra=None):
    env = os.environ.copy()
    env.pop("ABS_STRIPE_SECRET_KEY", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(_script_path()), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_annual_dry_run_lists_3_annual_skus():
    result = _run(
        ["--mode", "test", "--dry-run", "--annual"],
        env_extra={"ABS_STRIPE_SECRET_KEY": "sk_test_x"},
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "self-host-annual" in out
    assert "team-5-annual" in out
    assert "team-10-annual" in out
    assert out.count("WOULD-CREATE") == 3


def test_default_dry_run_still_uses_one_time_skus():
    """--annual yokken eski 3 SKU (one-time) gelir."""
    result = _run(
        ["--mode", "test", "--dry-run"],
        env_extra={"ABS_STRIPE_SECRET_KEY": "sk_test_x"},
    )
    assert result.returncode == 0
    assert "self-host-annual" not in result.stdout
    assert "self-host" in result.stdout
    assert result.stdout.count("WOULD-CREATE") == 3
