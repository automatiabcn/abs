"""Senior judge — AST metrikleri + fingerprint + LLM call (mock)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.judge.ast_metrics import ast_metrics, extract_added_lines, fingerprint_distance
from app.judge.senior import judge_diff


def test_extract_added_lines_skips_triple_plus_header():
    diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new code\n"
    added = extract_added_lines(diff)
    assert "new code" in added
    assert "+++" not in added


def test_ast_metrics_counts_funcs_and_docstrings():
    code = '''
def a():
    """doc a."""
    return 1

def b(x: int) -> int:
    return x

async def c(y):
    pass
'''
    m = ast_metrics(code)
    assert m["n_funcs"] == 3
    assert 0.33 <= m["docstring_ratio"] <= 0.34
    assert 0.33 <= m["type_hints_ratio"] <= 0.34


def test_fingerprint_distance_zero_when_match():
    m = {"docstring_ratio": 0.6, "type_hints_ratio": 0.7}
    persona = {"docstring_ratio": 0.6, "type_hints_ratio": 0.7}
    assert fingerprint_distance(m, persona) == 0.0


def test_fingerprint_distance_func_length_adds_small_signal():
    persona = {"docstring_ratio": 0.6, "type_hints_ratio": 0.7, "avg_func_lines": 20.0}
    match = {"docstring_ratio": 0.6, "type_hints_ratio": 0.7, "avg_func_lines": 20.0}
    far = {"docstring_ratio": 0.6, "type_hints_ratio": 0.7, "avg_func_lines": 120.0}
    assert fingerprint_distance(match, persona) == 0.0
    # A large function-length gap contributes signal...
    assert fingerprint_distance(far, persona) > 0.0
    # ...but never dominates (stays a small fraction of the total distance).
    assert fingerprint_distance(far, persona) < 0.2


@pytest.mark.asyncio
async def test_judge_diff_llm_mocked(monkeypatch):
    from app.judge import senior as sj

    fake = AsyncMock()
    fake.call = AsyncMock(
        return_value=type(
            "R", (), {"text": '{"score": 8.0, "teaching": "naming iyi"}'}
        )()
    )
    monkeypatch.setattr(sj, "get_provider", lambda _: fake)

    diff = (
        "--- a/x.py\n+++ b/x.py\n@@ -1 +1,3 @@\n"
        "+def fib(n: int) -> int:\n"
        '+    """Fibonacci."""\n'
        "+    return n if n < 2 else fib(n-1)+fib(n-2)\n"
    )
    result = await judge_diff(diff, "x.py")
    assert 0 <= result["combined_score"] <= 10
    assert result["ast_score"] is not None
    assert result["llm_score"] == 8.0


@pytest.mark.asyncio
async def test_judge_file_grades_whole_file(monkeypatch, tmp_path):
    from app.judge import senior as sj

    fake = AsyncMock()
    fake.call = AsyncMock(
        return_value=type("R", (), {"text": '{"score": 7.0, "teaching": "ok"}'})()
    )
    monkeypatch.setattr(sj, "get_provider", lambda _: fake)

    f = tmp_path / "m.py"
    f.write_text(
        'def fib(n: int) -> int:\n    """Fibonacci."""\n'
        "    return n if n < 2 else fib(n - 1) + fib(n - 2)\n"
    )
    result = await sj.judge_file(str(f))
    assert 0 <= result["combined_score"] <= 10
    assert result["ast_score"] is not None
    assert result["llm_score"] == 7.0


@pytest.mark.asyncio
async def test_judge_file_missing_file_is_graceful():
    from app.judge import senior as sj

    result = await sj.judge_file("/nonexistent/nope.py")
    assert result["combined_score"] == 0.0
    assert result["ast_score"] is None


@pytest.mark.asyncio
async def test_llm_judge_sees_the_diff_not_just_added_lines(monkeypatch):
    """Live tour: a correct one-line edit scored 2/10 because the judge only saw
    `return 2` with no idea what it replaced. The prompt must carry the diff and
    the file, or the moat feature grades fragments instead of changes."""
    from app.judge import senior as sj

    seen = {}

    async def _capture(prompt, **kwargs):
        seen["prompt"] = prompt
        return type("R", (), {"text": '{"score": 9.0, "teaching": "ok"}'})()

    fake = AsyncMock()
    fake.call = _capture
    monkeypatch.setattr(sj, "get_provider", lambda _: fake)

    diff = "--- util.py\n+++ util.py\n@@ -1,2 +1,2 @@\n def helper():\n-    return 1\n+    return 2\n"
    result = await judge_diff(diff, "util.py")

    assert "-    return 1" in seen["prompt"], "the judge never saw what was replaced"
    assert "util.py" in seen["prompt"], "the judge never saw which file it lands in"
    assert result["llm_score"] == 9.0
