"""One release version, stamped once, enforced at the gate.

By 2026-08 the repo carried four different version numbers at once: git tags
were at v1.0.10, while pyproject.toml, app/config.py and the landing
package.json all still said 1.0.6 — so /healthz, the update check and the
release page disagreed about what a customer was running, and nothing noticed.

Two pieces close that class:
- scripts/bump_version.sh rewrites every stamp in one command, and
- the release workflow refuses a tag whose stamps were not bumped.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
BUMP = REPO / "scripts" / "bump_version.sh"
RELEASE_YML = REPO / ".github" / "workflows" / "release.yml"
STAMPS = (
    "core/backend/pyproject.toml",
    "core/backend/app/config.py",
    "core/landing/package.json",
)


def test_the_release_gate_checks_every_stamp():
    """A gate that greps two of three files lets the third drift forever."""
    text = RELEASE_YML.read_text(encoding="utf-8")
    assert "Version stamps match the tag" in text, "release.yml has no stamp gate"
    gate = text[text.index("Version stamps match the tag") :]
    gate = gate[: gate.index("Identify tag metadata")]
    for stamp in STAMPS:
        assert stamp in gate, f"the stamp gate does not check {stamp}"
    assert "exit 1" in gate, "a stamp mismatch does not stop the release"
    assert "bump_version.sh" in gate, "the failure does not say how to fix itself"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
def test_bump_rewrites_every_stamp(tmp_path):
    """Run the real script against a copied tree and read the stamps back."""
    for rel in STAMPS:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, dst)

    proc = subprocess.run(
        ["bash", str(BUMP), "9.9.9"],
        env={"ABS_REPO_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr

    assert 'version = "9.9.9"' in (tmp_path / STAMPS[0]).read_text()
    config = (tmp_path / STAMPS[1]).read_text()
    assert 'version: str = "9.9.9"' in config
    # The first run of this script hit every `*version: str = "..."` field in
    # config.py at once — demo_seed_version and vault_min_sops_version came out
    # stamped "1.1.0". Only the release stamp may move.
    assert 'demo_seed_version: str = "9.9.9"' not in config, (
        "bump rewrote demo_seed_version — the sed is not anchored to the "
        "release stamp"
    )
    assert 'vault_min_sops_version: str = "9.9.9"' not in config, (
        "bump rewrote vault_min_sops_version — the sed is not anchored to the "
        "release stamp"
    )
    assert '"version": "9.9.9"' in (tmp_path / STAMPS[2]).read_text()


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
def test_bump_refuses_a_leading_v_and_non_semver(tmp_path):
    """`bump_version.sh v1.1.0` stamping the literal string `v1.1.0` would fail
    the gate on every file at once — refuse it at the door instead."""
    for arg in ("v1.1.0", "not-a-version"):
        proc = subprocess.run(
            ["bash", str(BUMP), arg],
            env={"ABS_REPO_ROOT": str(tmp_path), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode != 0, f"accepted {arg!r}"
