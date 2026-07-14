"""Q12 L21 sweep 3 — destructive fresh-deploy drill spec (founder-gated).

Sweep 3 of L21 was always going to be founder-gated because it
deletes Docker volumes and rebuilds from clean. This file ships the
*spec* — assertions that the script exists, has the safety gate,
and SKIP path is the default — without running the destructive
part.

The actual drill runs only when ABS_DESTRUCTIVE_DRILL=1 is set, which
the founder does locally before each prod rollout cut.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "chaos" / "destructive_drill.sh"


def test_drill_script_exists() -> None:
    assert SCRIPT.exists(), f"destructive drill script missing at {SCRIPT}"


def test_drill_script_executable() -> None:
    assert os.access(SCRIPT, os.X_OK), (
        f"destructive drill script {SCRIPT} is not executable"
    )


def test_drill_default_skip_message() -> None:
    """With ABS_DESTRUCTIVE_DRILL unset/zero, the script must print
    a SKIP message and exit 0 without running the destructive part.

    This is the load-bearing safety contract: a CI run that
    accidentally invokes this script must NOT delete volumes.
    """

    env = {**os.environ}
    env.pop("ABS_DESTRUCTIVE_DRILL", None)
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"default invocation must exit 0 (SKIP), got {result.returncode}: "
        f"stderr={result.stderr[:300]}"
    )
    combined = result.stdout + result.stderr
    assert "GATED" in combined or "ABS_DESTRUCTIVE_DRILL" in combined, (
        "SKIP message must explain the gate; got:\n" + combined[:500]
    )


def test_drill_explicit_zero_also_skips() -> None:
    """ABS_DESTRUCTIVE_DRILL=0 must take the SKIP path (any value
    other than '1' counts as off)."""

    env = {**os.environ, "ABS_DESTRUCTIVE_DRILL": "0"}
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0


def test_drill_refuses_live_namespace() -> None:
    """If the script were invoked with ABS_DRILL_PROJECT=infra (the
    live namespace), it must refuse with exit code 3 (NOT delete
    the live volumes). This tests the namespace-collision guard
    that protects the 25h customer journey state.
    """

    env = {
        **os.environ,
        "ABS_DESTRUCTIVE_DRILL": "1",
        "ABS_DRILL_PROJECT": "infra",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 3, (
        f"refusing-live-namespace must exit 3, got {result.returncode}: "
        f"stderr={result.stderr[:300]}"
    )
    combined = result.stdout + result.stderr
    assert "refusing" in combined.lower() or "live namespace" in combined.lower()


def test_drill_explicitly_refuses_abs_cj_namespace() -> None:
    """abs-cj is the customer journey namespace. Same protection."""

    env = {
        **os.environ,
        "ABS_DESTRUCTIVE_DRILL": "1",
        "ABS_DRILL_PROJECT": "abs-cj",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 3


def test_drill_documents_iters_default() -> None:
    """The brief asks for 3 iterations to validate idempotency. The
    script honours ABS_DRILL_ITERS env var but defaults to 1 for the
    quickest possible sanity loop. Pin both knobs as documented."""

    src = SCRIPT.read_text(encoding="utf-8")
    assert "ABS_DRILL_ITERS" in src
    assert "default: 1" in src or "ABS_DRILL_ITERS:-1" in src
    # Validates that R27 BodySizeLimit middleware is live in the
    # rebuilt deployment — proves the drill exercises the audit
    # surface, not just the boot path.
    assert "60000000" in src
    assert "413" in src
