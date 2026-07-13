# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""AST metrics — docstring ratio, type hint ratio, average function length."""

from __future__ import annotations

import ast
from typing import Dict


def extract_added_lines(diff_text: str) -> str:
    """Pull the added lines out of a unified diff, without the '+' marker."""
    lines = []
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
    return "\n".join(lines)


def ast_metrics(code: str) -> Dict[str, float]:
    """AST metrics for a Python snippet. Unparseable code yields {}."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}

    n_funcs = 0
    n_funcs_doc = 0
    n_funcs_types = 0
    func_lines = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n_funcs += 1
            if ast.get_docstring(node):
                n_funcs_doc += 1
            annotated = sum(1 for a in node.args.args if a.annotation)
            if annotated or node.returns:
                n_funcs_types += 1
            start = getattr(node, "lineno", 0)
            end = getattr(node, "end_lineno", start)
            if end > start:
                func_lines.append(end - start + 1)

    return {
        "n_funcs": float(n_funcs),
        "docstring_ratio": (n_funcs_doc / n_funcs) if n_funcs else 0.0,
        "type_hints_ratio": (n_funcs_types / n_funcs) if n_funcs else 0.0,
        "avg_func_lines": (sum(func_lines) / len(func_lines)) if func_lines else 0.0,
    }


def fingerprint_distance(metrics: Dict[str, float], persona: Dict[str, float]) -> float:
    """Mean absolute distance from the persona targets, in 0..1."""
    if not metrics or not persona:
        return 0.0
    keys = ("docstring_ratio", "type_hints_ratio")
    deltas = []
    for k in keys:
        target = persona.get(k, 0.0)
        actual = metrics.get(k, 0.0)
        deltas.append(abs(actual - target))
    if not deltas:
        return 0.0
    return sum(deltas) / len(deltas)
