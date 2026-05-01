"""024 Modul G — Docker compose smoke script existence + validity."""

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
        / "compose_smoke.sh"
    )


def _compose_file() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "infra"
        / "docker-compose.yml"
    )


def test_compose_smoke_script_exists_and_executable():
    p = _script()
    assert p.is_file()
    # Owner-executable
    assert os.access(p, os.X_OK), f"script not executable: {p}"
    text = p.read_text(encoding="utf-8")
    assert "#!/usr/bin/env bash" in text
    assert "docker compose" in text
    assert "/healthz" in text


def test_compose_yml_valid_via_docker_config():
    """`docker compose -f docker-compose.yml config` must succeed (syntax/schema).

    If Docker is not installed in the environment, skip gracefully.
    """
    if not shutil.which("docker"):
        return
    proc = subprocess.run(
        ["docker", "compose", "-f", str(_compose_file()), "config"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr[:300]
    # Output should mention our services
    assert "backend" in proc.stdout or "abs-backend" in proc.stdout
