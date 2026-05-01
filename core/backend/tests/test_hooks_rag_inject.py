"""rag_inject — STUB davranış (009'a kadar placeholder)."""

from __future__ import annotations

import pytest

from app.config import settings
from app.hooks import rag_inject


@pytest.fixture(autouse=True)
def _tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))


def test_bash_analyze_triggers_stub_context():
    msg = rag_inject.maybe_rag_inject(
        "Bash", {"command": "python3 analyze data for trends"}
    )
    assert "STUB" in msg or "009" in msg


def test_write_python_file_triggers_stub():
    msg = rag_inject.maybe_rag_inject(
        "Write", {"file_path": "/x/y.py", "content": "print(1)"}
    )
    assert "STUB" in msg or "009" in msg


def test_other_tools_no_context():
    msg = rag_inject.maybe_rag_inject("Read", {"file_path": "/x"})
    assert msg == ""


def test_rate_limit_same_category():
    a = rag_inject.maybe_rag_inject("Write", {"file_path": "/a.py", "content": "x"})
    b = rag_inject.maybe_rag_inject("Write", {"file_path": "/b.py", "content": "y"})
    assert a != ""
    assert b == ""  # aynı kategori için 5dk içinde tek context
