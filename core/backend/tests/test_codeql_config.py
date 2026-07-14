# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""CodeQL config sanity tests.

The repo ships `.github/codeql/codeql-config.yml` to exclude
`py/path-injection` on `_safe_path` helper + 3 call sites + piper server.
GitHub default setup picks up this file automatically. We assert the file
parses, names the expected exclusion rule, and lists the 5 expected paths,
so a refactor that renames the helper without updating the config will
fail the test (and the worker will know to re-add the FP).
"""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / ".github" / "codeql" / "codeql-config.yml"


def test_codeql_config_file_exists() -> None:
    assert CONFIG_PATH.is_file(), f"missing: {CONFIG_PATH}"


def test_codeql_config_is_valid_yaml() -> None:
    data = yaml.safe_load(CONFIG_PATH.read_text())
    assert isinstance(data, dict)
    assert data.get("name")


def test_codeql_config_uses_security_extended_suite() -> None:
    data = yaml.safe_load(CONFIG_PATH.read_text())
    suites = [q.get("uses") for q in (data.get("queries") or [])]
    assert "security-extended" in suites
    assert "security-and-quality" in suites


def test_codeql_config_excludes_path_injection_on_safe_path() -> None:
    data = yaml.safe_load(CONFIG_PATH.read_text())
    filters = data.get("query-filters") or []
    assert filters, "query-filters block missing"

    path_injection_excludes = [
        f["exclude"]
        for f in filters
        if isinstance(f, dict)
        and "exclude" in f
        and f["exclude"].get("id") == "py/path-injection"
    ]
    assert path_injection_excludes, "py/path-injection exclude missing"

    excluded_paths = path_injection_excludes[0].get("paths") or []
    expected = {
        "core/backend/app/symbols/_safe_path.py",
        "core/backend/app/symbols/parser.py",
        "core/backend/app/symbols/index.py",
        "core/backend/app/symbols/typescript_parser.py",
        "infra/piper/server.py",
    }
    assert set(excluded_paths) == expected, (
        f"path drift — got {excluded_paths}, expected {expected}"
    )


def test_codeql_config_ignores_venv_and_next_build() -> None:
    data = yaml.safe_load(CONFIG_PATH.read_text())
    ignores = data.get("paths-ignore") or []
    assert "core/backend/.venv/**" in ignores
    assert "core/landing/.next/**" in ignores
    assert "**/__pycache__/**" in ignores
