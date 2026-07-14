"""Escrow setup script syntax + dry-run options."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _script() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "infra"
        / "scripts"
        / "vault_escrow_setup.sh"
    )


def test_escrow_script_exists_and_syntax_clean():
    p = _script()
    assert p.is_file()
    assert os.access(p, os.X_OK)
    text = p.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in text
    assert "set -euo pipefail" in text
    for marker in ("onepassword", "s3", "zip", "--dry-run", "ABS Production"):
        assert marker in text, f"missing marker: {marker}"
    if shutil.which("bash"):
        proc = subprocess.run(
            ["bash", "-n", str(p)], capture_output=True, text=True, timeout=10
        )
        assert proc.returncode == 0, proc.stderr


def test_escrow_dry_run_prints_target_options(tmp_path):
    if not shutil.which("bash"):
        return
    fake_key = tmp_path / "age.txt"
    fake_key.write_text("# public key: age1mock\nAGE-SECRET-KEY-1MOCK\n")

    proc = subprocess.run(
        [
            "bash",
            str(_script()),
            "--target",
            "onepassword",
            "--key",
            str(fake_key),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    combined = (proc.stderr or "") + (proc.stdout or "")
    assert "DRY-RUN" in combined
    assert "1Password" in combined
