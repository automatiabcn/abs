"""
Q12-L28 R77 — backup-restore DR drill spec contract.

Locks behaviour of `scripts/dr/backup_restore_drill.sh`:

1. DRY RUN by default (no ABS_DR_DRILL=1) — exit 0, prints gate banner,
   does NOT execute backup/restore commands.
2. Refuses to run against live or sister namespaces (`infra`, `abs-cj`,
   `abs`, `q12-l21-drill`) even with ABS_DR_DRILL=1 — exit 3.
3. With ABS_DR_DRILL=1 + sandbox namespace, exit 0 with a banner pointing
   at the founder-gated round artifact (actual-run body intentionally
   unimplemented in R77).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "dr" / "backup_restore_drill.sh"


def _run(env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(env_extra)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
        cwd=str(REPO_ROOT),
    )


def test_script_exists_and_is_executable():
    assert SCRIPT.exists(), f"DR drill script missing: {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), "script not executable (chmod +x)"


def test_dry_run_default_exits_zero_with_gate_banner():
    result = _run({"ABS_DR_DRILL": "0"})
    assert result.returncode == 0, result.stderr
    assert "DR backup-restore drill is GATED" in result.stdout
    assert "DRY RUN only" in result.stdout
    # Must not have actually run pg_dump / docker / aws
    assert "pg_dump" not in result.stderr
    assert "docker compose" not in result.stderr.lower() or "DRY RUN" in result.stdout


def test_unset_env_treated_as_dry_run():
    result = _run({})  # explicitly unset / inherit
    # If ABS_DR_DRILL leaks from the environment we make it dry-run anyway
    if os.environ.get("ABS_DR_DRILL") == "1":
        pytest.skip("ABS_DR_DRILL=1 in env (founder run); DRY RUN test n/a")
    assert result.returncode == 0
    assert "GATED" in result.stdout


@pytest.mark.parametrize(
    "namespace",
    ["infra", "abs-cj", "abs", "q12-l21-drill"],
)
def test_refuses_live_or_sister_namespace(namespace: str):
    result = _run(
        {"ABS_DR_DRILL": "1", "ABS_DR_DRILL_PROJECT": namespace},
    )
    assert result.returncode == 3, f"expected refusal exit 3, got {result.returncode}"
    assert "refusing" in result.stderr.lower() or "refusing" in result.stdout.lower()
    assert namespace in (result.stderr + result.stdout)


def test_sandbox_namespace_with_gate_open_keeps_actual_run_unshipped():
    """R77 ships the spec + safety contract only; the actual-run body is left
    unimplemented so the founder approval gate stays meaningful."""
    result = _run(
        {"ABS_DR_DRILL": "1", "ABS_DR_DRILL_PROJECT": "q12-dr-drill"},
    )
    assert result.returncode == 0, result.stderr
    assert "actual-run body is intentionally" in result.stdout
    assert "round_77_dr_drill_spec.md" in result.stdout


def test_documents_isolated_port_and_default_tenant_count():
    """The dry-run banner must surface the defaults so a reader can audit
    the proposed isolation without reading the script source."""
    result = _run({"ABS_DR_DRILL": "0"})
    out = result.stdout
    assert "port 28100" in out, "default port must be advertised in dry run"
    assert "3 synthetic" in out, "default tenant count must be advertised"
    assert "Postgres + Qdrant + Helm release are never contacted" in out


def test_refusal_predates_gate_check():
    """Even with ABS_DR_DRILL unset, attempting an unsafe namespace must
    error early so a typo cannot ride a future gate flip into prod."""
    # ABS_DR_DRILL not set → still hits namespace refusal first
    result = _run({"ABS_DR_DRILL_PROJECT": "infra"})
    assert result.returncode == 3
    assert "refusing" in result.stderr.lower()
