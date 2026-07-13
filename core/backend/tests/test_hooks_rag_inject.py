"""rag_inject — real hits from the operator's own index, or nothing."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.config import settings
from app.hooks import rag_inject


@pytest.fixture(autouse=True)
def _tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))


def _hits(monkeypatch, hits: List[Dict[str, Any]]) -> None:
    """Stand in for the index without standing in for the hook's own rules."""
    monkeypatch.setattr(rag_inject, "_run_blocking", lambda _coro: hits)


def test_analysis_gets_context_from_the_index(monkeypatch):
    _hits(monkeypatch, [
        {"file": "reports/q3.md", "snippet": "Revenue grew 14% on the retainer accounts.", "score": 0.82},
    ])
    msg = rag_inject.maybe_rag_inject(
        "Bash", {"command": "python3 analyze data for trends"}
    )
    assert "reports/q3.md" in msg
    assert "Revenue grew 14%" in msg


def test_writing_code_gets_context_from_the_index(monkeypatch):
    _hits(monkeypatch, [
        {"file": "app/billing.py", "snippet": "def charge(...)", "score": 0.7},
    ])
    msg = rag_inject.maybe_rag_inject(
        "Write", {"file_path": "/x/y.py", "content": "print(1)"}
    )
    assert "app/billing.py" in msg


def test_an_empty_index_says_nothing(monkeypatch):
    # The old version shipped a placeholder here. A placeholder reads as
    # context and carries none — worse than silence, because the model
    # believes it.
    _hits(monkeypatch, [])
    msg = rag_inject.maybe_rag_inject(
        "Write", {"file_path": "/x/y.py", "content": "print(1)"}
    )
    assert msg == ""


def test_a_weak_match_says_nothing(monkeypatch):
    # A 0.1 similarity is the index shrugging. Injected, it would look exactly
    # as authoritative as a real hit.
    _hits(monkeypatch, [
        {"file": "unrelated.md", "snippet": "Office plants need watering.", "score": 0.1},
    ])
    msg = rag_inject.maybe_rag_inject(
        "Write", {"file_path": "/x/y.py", "content": "print(1)"}
    )
    assert msg == ""


def test_a_broken_index_never_breaks_the_tool_call(monkeypatch):
    def _boom(_coro):
        raise RuntimeError("qdrant unreachable")

    monkeypatch.setattr(rag_inject, "_run_blocking", _boom)
    msg = rag_inject.maybe_rag_inject(
        "Write", {"file_path": "/x/y.py", "content": "print(1)"}
    )
    assert msg == ""


def test_other_tools_no_context():
    msg = rag_inject.maybe_rag_inject("Read", {"file_path": "/x"})
    assert msg == ""


def test_rate_limit_same_category(monkeypatch):
    _hits(monkeypatch, [
        {"file": "app/billing.py", "snippet": "def charge(...)", "score": 0.7},
    ])
    a = rag_inject.maybe_rag_inject("Write", {"file_path": "/a.py", "content": "x"})
    b = rag_inject.maybe_rag_inject("Write", {"file_path": "/b.py", "content": "y"})
    assert a != ""
    assert b == ""  # one context per category per five minutes
