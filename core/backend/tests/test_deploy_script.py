"""Hetzner deploy script syntax + chmod check."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _script() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "infra" / "scripts" / "deploy_hetzner.sh"
    )


def test_deploy_script_exists_executable_and_syntax_clean():
    p = _script()
    assert p.is_file()
    assert os.access(p, os.X_OK), f"script not executable: {p}"

    text = p.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in text
    assert "set -euo pipefail" in text
    # Required steps
    for marker in (
        "docker",
        "Caddyfile",
        "age",
        "compose",
        "healthz",
        "--domain",
        "--email",
        # A deploy that tracks `main` runs whatever the branch held that day;
        # the script must be able to pin a release and record it for compose.
        "--version",
        "ABS_VERSION=",
        # The repo tracks infra/Caddyfile, so "write only if missing" never
        # fired — every install kept the dev config serving abs.local and the
        # promised domain + ACME setup was silently skipped. The script must
        # overwrite the untouched repo default and must carry an operator's
        # edited config across the upgrade checkout.
        "diff --quiet -- infra/Caddyfile",
        "restored the deployed Caddyfile",
    ):
        assert marker in text, f"missing marker: {marker}"

    # bash -n syntax check (skip if bash unavailable)
    if shutil.which("bash"):
        proc = subprocess.run(
            ["bash", "-n", str(p)], capture_output=True, text=True, timeout=10
        )
        assert proc.returncode == 0, proc.stderr
