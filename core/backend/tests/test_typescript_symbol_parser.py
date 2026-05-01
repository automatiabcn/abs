"""022 Modul H — TS/JS regex symbol parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.symbols.typescript_parser import is_ts_or_js, parse_typescript_file


@pytest.fixture()
def _ts_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.ts"
    p.write_text(
        """
import { foo } from 'react';
import bar from './bar';

export interface User {
  id: number;
  email: string;
}

export type Token = string;

export class UserService {
  fetch(id: number) {}
}

export function getUser(id: number) {
  return null;
}

export const formatName = (u: User) => `${u.email}`;

async function login(email: string, pw: string) {
  return true;
}
""",
        encoding="utf-8",
    )
    return p


def test_is_ts_or_js_extensions():
    assert is_ts_or_js(Path("a.ts"))
    assert is_ts_or_js(Path("a.tsx"))
    assert is_ts_or_js(Path("a.js"))
    assert is_ts_or_js(Path("a.jsx"))
    assert is_ts_or_js(Path("a.mjs"))
    assert not is_ts_or_js(Path("a.py"))


def test_typescript_parser_extracts_classes_functions_imports(_ts_file):
    syms = parse_typescript_file(_ts_file)
    names = {s.name for s in syms}
    # Class
    assert "UserService" in names
    # Interface (kind=class)
    assert "User" in names
    # Type alias (kind=class)
    assert "Token" in names
    # Functions
    assert "getUser" in names
    assert "login" in names
    # Arrow function const
    assert "formatName" in names
    # Imports
    import_names = {s.name for s in syms if s.kind == "import"}
    assert "react" in import_names
    assert "./bar" in import_names


def test_parse_directory_includes_typescript():
    """parse_directory `.ts` dosyalarını da yakalar (016 hybrid retrieval için)."""
    import tempfile

    from app.symbols.parser import parse_directory

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        (td_path / "x.ts").write_text(
            "export class HelloComp { render() {} }\n", encoding="utf-8"
        )
        (td_path / "y.py").write_text("class PyClass:\n    pass\n", encoding="utf-8")

        syms = parse_directory(td_path)
        names = {s.name for s in syms}
        assert "HelloComp" in names
        assert "PyClass" in names
