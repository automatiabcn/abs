"""delegate_nudge — inline python3 -c + big docs Write."""

from __future__ import annotations

import pytest

from app.config import settings
from app.hooks import delegate_nudge


@pytest.fixture(autouse=True)
def _tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", str(tmp_path))


def test_inline_python_analyze_triggers_nudge():
    msg = delegate_nudge.maybe_delegate_nudge(
        "Bash",
        {"command": "python3 -c 'data=[1,2,3]; analyze(data); calculate(data)'"},
    )
    assert "DELEGATE" in msg
    assert "gptoss" in msg


def test_curl_python_pipe_triggers_nudge():
    msg = delegate_nudge.maybe_delegate_nudge(
        "Bash",
        {"command": "curl -s https://api.example/data | python3 -c 'import sys'"},
    )
    assert "DELEGATE" in msg
    assert "curl" in msg


def test_inline_python_file_op_does_not_trigger():
    msg = delegate_nudge.maybe_delegate_nudge(
        "Bash",
        {"command": "python3 -c 'import ast; ast.parse(open(\"x.py\").read())'"},
    )
    assert msg == ""


def test_big_turkish_docs_write_triggers_qwen32b_nudge():
    content = "# README\n\n" + ("Türkçe içerik açıklaması. " * 200)
    msg = delegate_nudge.maybe_delegate_nudge(
        "Write",
        {"file_path": "/proj/docs/README.md", "content": content},
    )
    assert "qwen32b" in msg
    assert "Büyük docs" in msg


def test_small_docs_does_not_trigger():
    msg = delegate_nudge.maybe_delegate_nudge(
        "Write",
        {"file_path": "/proj/docs/README.md", "content": "kısa"},
    )
    assert msg == ""


def test_code_heavy_docs_does_not_trigger():
    # 12 code blocks → code heavy, delege etmemeli
    content = ("# Guide\n\n" + "```python\nx=1\n```\n\n") * 12
    content += "Ek metin " * 500
    msg = delegate_nudge.maybe_delegate_nudge(
        "Write",
        {"file_path": "/proj/GUIDE.md", "content": content},
    )
    assert msg == ""
