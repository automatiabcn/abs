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
        '+def fib(n: int) -> int:\n'
        '+    """Fibonacci."""\n'
        "+    return n if n < 2 else fib(n-1)+fib(n-2)\n"
    )
    result = await judge_diff(diff, "x.py")
    assert 0 <= result["combined_score"] <= 10
    assert result["ast_score"] is not None
    assert result["llm_score"] == 8.0
