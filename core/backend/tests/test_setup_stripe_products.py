"""017 — setup_stripe_products.py argparse + live-mode safeguard testleri."""

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
    # Test ortam stripe config'inin script'i etkilememesi icin temizle
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


def test_dry_run_no_stripe_call():
    """--dry-run hicbir API cagirmaz, stdout WOULD-CREATE satirlari icermeli."""
    result = _run(
        ["--mode", "test", "--dry-run"],
        env_extra={"ABS_STRIPE_SECRET_KEY": "sk_test_dummy"},
    )
    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    # 3 SKU icin WOULD-CREATE satiri
    assert result.stdout.count("WOULD-CREATE") == 3
    # Stripe live API erismez (real API hata verirdi)
    assert "self-host" in result.stdout
    assert "team-5" in result.stdout
    assert "team-10" in result.stdout


def test_mode_live_with_test_key_aborts():
    """--mode live + sk_test_ → exit code 2."""
    result = _run(
        ["--mode", "live"],
        env_extra={"ABS_STRIPE_SECRET_KEY": "sk_test_xyz"},
    )
    assert result.returncode == 2
    assert "SECURITY" in result.stderr


def test_mode_test_with_live_key_aborts():
    """--mode test + sk_live_ → exit code 2 (yanlis key live mode'a yansimasin)."""
    result = _run(
        ["--mode", "test"],
        env_extra={"ABS_STRIPE_SECRET_KEY": "sk_live_xyz"},
    )
    assert result.returncode == 2
    assert "SECURITY" in result.stderr


def test_no_key_env_returns_1():
    """ABS_STRIPE_SECRET_KEY yok → exit 1."""
    result = _run(["--mode", "test"])
    assert result.returncode == 1
    assert "ABS_STRIPE_SECRET_KEY" in result.stderr
