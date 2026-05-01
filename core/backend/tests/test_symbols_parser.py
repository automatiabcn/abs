"""016 — Python AST symbol parser + SQLite store testleri."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def isolated_data_dir(monkeypatch, tmp_path: Path):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    return tmp_path


def _write_py(path: Path, src: str) -> Path:
    path.write_text(src, encoding="utf-8")
    return path


def test_parse_python_file_extracts_functions(tmp_path: Path):
    from app.symbols.parser import parse_python_file

    f = _write_py(
        tmp_path / "a.py",
        "def foo():\n    return 1\n\nasync def bar():\n    return 2\n",
    )
    syms = parse_python_file(f)
    fn_syms = [s for s in syms if s.kind == "function"]
    assert len(fn_syms) == 2
    names = {s.name for s in fn_syms}
    assert "foo" in names and "bar" in names


def test_parse_class_with_methods(tmp_path: Path):
    from app.symbols.parser import parse_python_file

    f = _write_py(
        tmp_path / "b.py",
        (
            "class Foo:\n"
            "    def m1(self):\n"
            "        return 1\n"
            "    def m2(self):\n"
            "        return 2\n"
        ),
    )
    syms = parse_python_file(f)
    kinds = {s.name: s.kind for s in syms}
    assert "Foo" in kinds and kinds["Foo"] == "class"
    assert "Foo.m1" in kinds and kinds["Foo.m1"] == "function"
    assert "Foo.m2" in kinds and kinds["Foo.m2"] == "function"
    # parent set
    m1 = next(s for s in syms if s.name == "Foo.m1")
    assert m1.parent == "Foo"


def test_parse_imports(tmp_path: Path):
    from app.symbols.parser import parse_python_file

    f = _write_py(tmp_path / "c.py", "import os\nfrom pathlib import Path\n")
    syms = parse_python_file(f)
    imports = [s for s in syms if s.kind == "import"]
    assert len(imports) == 2
    names = {s.name for s in imports}
    assert "os" in names
    assert "pathlib.Path" in names


def test_neighbors_depth_1(isolated_data_dir, tmp_path: Path):
    from app.symbols.parser import parse_python_file
    from app.symbols.store import bulk_insert, neighbors

    f = _write_py(
        tmp_path / "g.py",
        "def alpha():\n    beta()\n\ndef beta():\n    return 1\n",
    )
    syms = parse_python_file(f)
    bulk_insert(syms)
    res = neighbors("alpha", depth=1)
    assert res["status"] == "ok"
    names = {n["name"] for n in res["neighbors"]}
    assert "beta" in names


def test_search_substring_match(isolated_data_dir, tmp_path: Path):
    from app.symbols.parser import parse_python_file
    from app.symbols.store import bulk_insert, search

    f = _write_py(
        tmp_path / "calc.py",
        "def calculate_total(): return 1\ndef calculate_avg(): return 2\ndef render(): return 3\n",
    )
    syms = parse_python_file(f)
    bulk_insert(syms)
    res = search("calc", limit=10)
    names = {r["name"] for r in res}
    assert "calculate_total" in names
    assert "calculate_avg" in names
    assert "render" not in names


def test_index_path_inserts_and_returns_stats(isolated_data_dir, tmp_path: Path):
    from app.symbols.index import index_path

    _write_py(
        tmp_path / "x.py",
        "def f1(): pass\ndef f2(): pass\nclass K: pass\n",
    )
    res = index_path(str(tmp_path))
    assert res["indexed"] >= 3
    assert res["stats"]["total_symbols"] >= 3
    assert res["stats"]["by_kind"].get("function", 0) >= 2
    assert res["stats"]["by_kind"].get("class", 0) >= 1
