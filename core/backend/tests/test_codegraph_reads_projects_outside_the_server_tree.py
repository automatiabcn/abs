"""The code graph must read the project the developer opened — which is never
under the server's own cwd.

Audit 2026-08-18: `code_graph_build` on a project under ~/Main returned
`symbols: 0, edges: 0` with no error; the same tree under /tmp gave 6/6.
`parse_directory` confined the walk to the process-wide ALLOWED_ROOTS (server
cwd, /app, /tmp, /var/folders) and swallowed the PermissionError. Every
earlier live tour had used a /tmp project, so the badge looked alive.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.codegraph import graph as cg
from app.symbols import _safe_path, parser


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def helper():\n    return 1\n\n\ndef caller():\n    return helper()\n")
    return tmp_path


@pytest.fixture
def server_tree_elsewhere(monkeypatch, tmp_path: Path):
    """Make the process-wide allowed roots NOT contain the project — the shape
    of every real install, where the server runs in /app or its own checkout."""
    monkeypatch.setattr(_safe_path, "ALLOWED_ROOTS", (Path("/nonexistent-server-tree"),))


def test_a_project_outside_the_server_tree_is_parsed(project, server_tree_elsewhere, monkeypatch, tmp_path):
    monkeypatch.setattr(cg, "_db_path", lambda key: str(tmp_path / f"{key}.db"))
    res = cg.build(str(project), key="t")
    assert "error" not in res, res
    assert res["symbols"] >= 2, res
    assert res["edges"] >= 1, res


def test_parse_directory_still_refuses_outside_its_roots(project, server_tree_elsewhere):
    """Confinement did not go away — it moved to the workspace boundary."""
    assert parser.parse_directory(project) == []  # process-wide roots: not allowed
    with pytest.raises(PermissionError):
        parser.parse_directory(project, strict=True)
    assert len(parser.parse_directory(project, roots=[project])) >= 2


def test_a_symlink_out_of_the_workspace_is_not_followed(project, server_tree_elsewhere, tmp_path):
    outside = tmp_path.parent / f"outside-{os.getpid()}"
    outside.mkdir(exist_ok=True)
    (outside / "secret.py").write_text("def leaked():\n    return 0\n")
    try:
        os.symlink(outside / "secret.py", project / "pkg" / "link.py")
        names = {s.name for s in parser.parse_directory(project, roots=[project])}
        assert "leaked" not in names
        assert "helper" in names
    finally:
        (outside / "secret.py").unlink(missing_ok=True)
        outside.rmdir()


def test_an_unreadable_root_is_an_error_not_an_empty_graph(monkeypatch, tmp_path):
    """0 symbols and 'was not allowed to look' must not be the same answer."""
    monkeypatch.setattr(cg, "_db_path", lambda key: str(tmp_path / f"{key}.db"))
    monkeypatch.setattr(
        parser, "parse_directory",
        lambda *a, **k: (_ for _ in ()).throw(PermissionError("nope")),
    )
    monkeypatch.setattr(cg, "parse_directory", parser.parse_directory)
    res = cg.build(str(tmp_path), key="t2")
    assert res["symbols"] == 0
    assert "error" in res and "not readable" in res["error"]
