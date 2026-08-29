"""A diff that adds no function has no docstring ratio.

Live, 2026-08-28 (G12): ⌘K renamed one variable (-1/+1). The judge scored it
2.6 — "would not ship" — with "docstring_ratio: 0.00 vs target 0.60". The
edit touched no function; the 0.00 was the `if n_funcs else 0.0` fallback
compared against a persona target. A developer who sees that learns to
ignore the judge. Absent means not applicable, and the distance skips it.
"""

from __future__ import annotations

from app.judge.ast_metrics import ast_metrics, fingerprint_distance

PERSONA = {"docstring_ratio": 0.60, "type_hints_ratio": 0.70, "avg_func_lines": 12.0}


def test_no_functions_means_no_ratios():
    m = ast_metrics("resp = test_client.get('/market')\nassert resp.status_code == 200\n")
    assert m["n_funcs"] == 0.0
    assert "docstring_ratio" not in m
    assert "type_hints_ratio" not in m


def test_a_function_still_carries_its_ratios():
    m = ast_metrics("def f(a: int) -> int:\n    return a\n")
    assert m["n_funcs"] == 1.0
    assert m["docstring_ratio"] == 0.0
    assert m["type_hints_ratio"] == 1.0


def test_distance_is_neutral_when_no_ratio_applies():
    assert fingerprint_distance({"n_funcs": 0.0}, PERSONA) == 0.0


def test_distance_still_penalises_a_function_without_docstring():
    m = ast_metrics("def f(a):\n    return a\n")
    assert fingerprint_distance(m, PERSONA) > 0.3


def test_senior_ast_score_does_not_punish_a_rename():
    from app.judge.senior import _ast_score

    rename = ast_metrics("resp = test_client.get('/market')\n")
    bare_function = ast_metrics("def f(a):\n    return a\n")
    assert _ast_score(rename, PERSONA) == 10.0
    assert _ast_score(bare_function, PERSONA) < _ast_score(rename, PERSONA)
