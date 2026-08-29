"""Test files are not measured for type hints.

Review panel, live 2026-08-28 (G17): a sound new test file scored 3.6
"below 5", with `type_hints_ratio 0.00 vs target 0.70` as the biggest
delta. Tests take fixtures by name — `def test_x(client):` — and nobody
annotates them; the persona's hint target is a rule for product code.
"""

from __future__ import annotations

from app.judge.ast_metrics import fingerprint_distance
from app.judge.senior import applicable_metrics, is_test_path

PERSONA = {"docstring_ratio": 0.60, "type_hints_ratio": 0.70, "avg_func_lines": 12.0}
TEST_CODE = 'def test_a(client):\n    """Lists products."""\n    assert client.get("/market").status_code == 200\n'


def test_paths_pytest_collects_are_tests():
    for p in ["tests/test_market.py", "app/tests/x.py", "test_util.py", "pkg/util_test.py", "conftest.py", "a\\tests\\t.py"]:
        assert is_test_path(p), p
    for p in ["app/routes.py", "app/testing_tools.py", "contest.py", None, ""]:
        assert not is_test_path(p), p


def test_a_test_file_carries_no_type_hint_ratio():
    m = applicable_metrics(TEST_CODE, "tests/test_market.py")
    assert "type_hints_ratio" not in m
    assert m["docstring_ratio"] == 1.0


def test_product_code_still_does():
    m = applicable_metrics(TEST_CODE, "app/routes.py")
    assert m["type_hints_ratio"] == 0.0


def test_the_same_code_scores_better_as_a_test_than_as_product_code():
    as_test = fingerprint_distance(applicable_metrics(TEST_CODE, "tests/test_market.py"), PERSONA)
    as_code = fingerprint_distance(applicable_metrics(TEST_CODE, "app/routes.py"), PERSONA)
    assert as_test < as_code


def test_non_python_has_no_metrics():
    assert applicable_metrics("x", "a.ts") == {}
