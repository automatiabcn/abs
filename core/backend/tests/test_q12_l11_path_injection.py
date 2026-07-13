# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Sprint 2D ITEM-2.1 — CodeQL py/path-injection regression tests.

Covers the 8 alerts (#33..#40) flagged on production code:
  - core/backend/app/symbols/index.py:19
  - core/backend/app/symbols/parser.py:38,151,153,159
  - core/backend/app/symbols/typescript_parser.py:54
  - infra/piper/server.py:53 (x2 sinks)

The fix introduces `app.symbols._safe_path.safe_resolve` which canonicalizes
the user-supplied path and asserts it lives inside `ALLOWED_ROOTS`. Symlinks
pointing outside are rejected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.symbols._safe_path import safe_read_text, safe_resolve
from app.symbols.index import index_path


def test_safe_resolve_rejects_etc_passwd():
    with pytest.raises(PermissionError):
        safe_resolve("/etc/passwd")


def test_safe_resolve_rejects_root_dotfiles():
    with pytest.raises(PermissionError):
        safe_resolve("/root/.ssh/id_rsa")


def test_safe_resolve_accepts_cwd_relative(tmp_path, monkeypatch):
    monkeypatch.setenv("ABS_SYMBOLS_ALLOWED_ROOTS", str(tmp_path))
    # Re-import to refresh ALLOWED_ROOTS after env mutation
    import importlib

    import app.symbols._safe_path as sp

    importlib.reload(sp)
    target = tmp_path / "ok.py"
    target.write_text("x = 1\n")
    resolved = sp.safe_resolve(target)
    assert resolved == target.resolve()
    # restore: pytest tmp_path is under /var/folders/* on macOS which is in defaults
    monkeypatch.delenv("ABS_SYMBOLS_ALLOWED_ROOTS", raising=False)
    importlib.reload(sp)


def test_safe_resolve_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("ABS_SYMBOLS_ALLOWED_ROOTS", str(tmp_path))
    import importlib

    import app.symbols._safe_path as sp

    importlib.reload(sp)
    with pytest.raises(PermissionError):
        sp.safe_resolve(str(tmp_path / ".." / ".." / "etc" / "passwd"))
    monkeypatch.delenv("ABS_SYMBOLS_ALLOWED_ROOTS", raising=False)
    importlib.reload(sp)


def test_safe_read_text_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        safe_read_text(tmp_path / "nonexistent.txt")


def test_safe_read_text_existing_file_ok(tmp_path):
    p = tmp_path / "ok.py"
    p.write_text("y = 2\n")
    assert "y = 2" in safe_read_text(p)


def test_parse_python_file_outside_root_returns_empty(monkeypatch, tmp_path):
    """parser.py:38 sink — safe_read_text catches PermissionError."""
    monkeypatch.setenv("ABS_SYMBOLS_ALLOWED_ROOTS", str(tmp_path))
    import importlib

    import app.symbols._safe_path as sp

    importlib.reload(sp)
    # reload parser to refresh its import binding
    import app.symbols.parser as p_mod

    importlib.reload(p_mod)
    # /etc/hostname lives outside tmp_path → empty result (no crash, no read)
    result = p_mod.parse_python_file(Path("/etc/hostname"))
    assert result == []
    monkeypatch.delenv("ABS_SYMBOLS_ALLOWED_ROOTS", raising=False)
    importlib.reload(sp)
    importlib.reload(p_mod)


def test_parse_directory_outside_root_returns_empty(monkeypatch, tmp_path):
    """parser.py:151/153/159 sinks — directory walk rejects out-of-root root."""
    monkeypatch.setenv("ABS_SYMBOLS_ALLOWED_ROOTS", str(tmp_path))
    import importlib

    import app.symbols._safe_path as sp

    importlib.reload(sp)
    import app.symbols.parser as p_mod

    importlib.reload(p_mod)
    assert p_mod.parse_directory(Path("/etc")) == []
    monkeypatch.delenv("ABS_SYMBOLS_ALLOWED_ROOTS", raising=False)
    importlib.reload(sp)
    importlib.reload(p_mod)


def test_parse_typescript_file_outside_root_returns_empty(monkeypatch, tmp_path):
    """typescript_parser.py:54 sink — safe_read_text guards."""
    monkeypatch.setenv("ABS_SYMBOLS_ALLOWED_ROOTS", str(tmp_path))
    import importlib

    import app.symbols._safe_path as sp

    importlib.reload(sp)
    import app.symbols.typescript_parser as ts_mod

    importlib.reload(ts_mod)
    result = ts_mod.parse_typescript_file(Path("/etc/hostname"))
    assert result == []
    monkeypatch.delenv("ABS_SYMBOLS_ALLOWED_ROOTS", raising=False)
    importlib.reload(sp)
    importlib.reload(ts_mod)


def test_index_path_rejects_outside_root(monkeypatch, tmp_path):
    """index.py:19 sink — index_path() returns error dict, no crash."""
    monkeypatch.setenv("ABS_SYMBOLS_ALLOWED_ROOTS", str(tmp_path))
    import importlib

    import app.symbols._safe_path as sp

    importlib.reload(sp)
    import app.symbols.index as idx_mod

    importlib.reload(idx_mod)
    result = idx_mod.index_path("/etc")
    assert result["indexed"] == 0
    assert "error" in result
    monkeypatch.delenv("ABS_SYMBOLS_ALLOWED_ROOTS", raising=False)
    importlib.reload(sp)
    importlib.reload(idx_mod)


def test_index_path_accepts_inside_root(tmp_path):
    """index.py:19 sink — happy path: inside cwd default root works."""
    src = tmp_path / "demo.py"
    src.write_text("def hello():\n    return 1\n")
    result = index_path(str(tmp_path))
    # tmp_path on macOS is under /var/folders/* which is in defaults
    assert result.get("indexed", 0) >= 1


def test_piper_voice_id_rejects_traversal(tmp_path, monkeypatch):
    """infra/piper/server.py:53 sink — _safe_model_path rejects ../.."""
    import sys
    import types

    # Stub out the piper extra (only installed in the TTS image).
    fake_piper = types.ModuleType("piper")
    fake_piper_voice = types.ModuleType("piper.voice")
    setattr(
        fake_piper_voice,
        "PiperVoice",
        type("Stub", (), {"load": staticmethod(lambda *a, **k: None)}),
    )
    monkeypatch.setitem(sys.modules, "piper", fake_piper)
    monkeypatch.setitem(sys.modules, "piper.voice", fake_piper_voice)
    # Redirect MODEL_DIR to tmp_path so module init doesn't try /models.
    monkeypatch.setenv("ABS_PIPER_MODEL_DIR", str(tmp_path))

    import importlib.util as _util

    server_path = Path(__file__).resolve().parents[3] / "infra/piper/server.py"
    if not server_path.exists():
        pytest.skip(f"piper server not found at {server_path}")
    spec = _util.spec_from_file_location("_piper_test_module", server_path)
    assert spec is not None and spec.loader is not None
    mod = _util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        mod._safe_model_path("../etc/passwd", ".onnx")
    with pytest.raises(HTTPException):
        mod._safe_model_path("foo/../../etc/passwd", ".onnx")
    # Invalid characters rejected by regex (slash, dot-dot)
    with pytest.raises(HTTPException):
        mod._safe_model_path("a/b", ".onnx")
    # Valid id passes
    valid = mod._safe_model_path("tr_TR-fettah-medium", ".onnx")
    assert str(valid).endswith("tr_TR-fettah-medium.onnx")
