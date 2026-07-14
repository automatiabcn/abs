"""
fs-scan P0 allowlist coverage contract.

We don't run fs-scan from inside pytest (it's an MCP tool, not a Python
package), but we do lock the contract that every documented P0 source path
in the repository is either:

  (a) covered by an allowlist entry in .fs-scan-allowlist.yaml, OR
  (b) a real bug we have not yet fixed (in which case this test FAILS so we
      cannot land additional P0s without an explicit allowlist + review).

The test reads .fs-scan-allowlist.yaml and asserts each flagged path appears
in the `files` field of some allowlist entry.

If a future P0 lands at a new path, the worker MUST either:
  - fix the underlying issue (so fs-scan stops flagging the path), or
  - extend the allowlist with a why explaining the false positive

Either way, the contract makes sure no silent P0 backlog accumulates.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
ALLOWLIST_PATH = REPO_ROOT / ".fs-scan-allowlist.yaml"


# The full list of high-severity source paths the scanner flags. The
# contract: each must appear in the allowlist `files`. If the scanner stops
# flagging one of these (because we fix it for real), this test still
# passes — we only assert "documented", not "still flagged".
FLAGGED_PATHS = {
    # SQLModel ORM driver-API call sites (fs-scan misclassifies the API
    # name as a code-execution pattern; see SQLMODEL_DB_DRIVER_API entry)
    "core/backend/app/api/chat.py",
    "core/backend/app/api/mcp_tokens.py",
    "core/backend/app/api/admin/users.py",
    # Shell `${VAR:-default}` / `${VAR:?error}` parameter-expansion FPs
    "infra/docker-compose.demo.yml",
    "infra/docker-compose.langfuse.yml",
    "infra/docker-compose.qdrant.yml",
    "scripts/qdrant_backup.sh",
    "scripts/dr/backup_qdrant.sh",
}


@pytest.fixture(scope="module")
def allowlist():
    return yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def _allowlisted_paths(allowlist_doc: dict) -> set[str]:
    out: set[str] = set()
    for entry in allowlist_doc.get("allowlist", []):
        if "file" in entry:
            out.add(entry["file"])
        for f in entry.get("files", []) or []:
            out.add(f)
    return out


def test_allowlist_loads_with_required_top_level_keys(allowlist):
    assert "version" in allowlist
    assert "allowlist" in allowlist
    assert "policy" in allowlist
    assert allowlist["version"] >= 5


def test_every_allowlist_entry_has_why_and_review_owner(allowlist):
    for entry in allowlist["allowlist"]:
        assert "why" in entry, f"entry {entry.get('id')!r} missing 'why'"
        assert "review_owner" in entry, (
            f"entry {entry.get('id')!r} missing 'review_owner'"
        )
        # Body of `why` must be substantive — discourages stub allowlist entries.
        why = entry["why"].strip()
        assert len(why) > 60, (
            f"entry {entry.get('id')!r} has a too-short why ({len(why)} chars). "
            "Allowlist entries are documentation — explain the FP."
        )


def test_every_known_p0_source_path_is_documented(allowlist):
    """The load-bearing assertion. If fs-scan flags a path that this set
    enumerates, the path must appear in the allowlist `files`."""
    documented = _allowlisted_paths(allowlist)
    missing = sorted(FLAGGED_PATHS - documented)
    assert not missing, (
        "The following P0 source paths are still flagged by fs-scan but have "
        "no allowlist entry — either fix the underlying flag or document it:\n"
        + "\n".join(f"  - {p}" for p in missing)
    )


def test_docker_shell_env_defaults_entry_covers_known_pattern_files(allowlist):
    """Every `${VAR:-default}` / `${VAR:?msg}` shell-expansion FP must live
    under the single DOCKER_SHELL_ENV_DEFAULTS entry, not be sprinkled
    individually."""
    entry = next(
        (
            e
            for e in allowlist["allowlist"]
            if e.get("id") == "DOCKER_SHELL_ENV_DEFAULTS"
        ),
        None,
    )
    assert entry is not None, "missing DOCKER_SHELL_ENV_DEFAULTS allowlist entry"
    files = set(entry.get("files", []) or [])
    expected = {
        "infra/docker-compose.demo.yml",
        "infra/docker-compose.langfuse.yml",
        "infra/docker-compose.qdrant.yml",
        "scripts/qdrant_backup.sh",
        "scripts/dr/backup_qdrant.sh",
    }
    assert expected <= files, (
        f"DOCKER_SHELL_ENV_DEFAULTS missing paths: {expected - files}"
    )


def test_referenced_files_actually_exist(allowlist):
    """Documenting a path that no longer exists is dead weight. Every
    `file` / `files` entry in the allowlist must point at a real path."""
    documented = _allowlisted_paths(allowlist)
    # These two are exception entries from the monorepo carve-out — they are
    # *expected absences* from the repo root (Dockerfile / .eslintrc*).
    expected_absent = {"Dockerfile", ".eslintrc*"}
    missing_files: list[str] = []
    for path in sorted(documented):
        if path in expected_absent:
            continue
        if not (REPO_ROOT / path).exists():
            missing_files.append(path)
    assert not missing_files, (
        "Allowlist references files that do not exist:\n"
        + "\n".join(f"  - {p}" for p in missing_files)
    )
