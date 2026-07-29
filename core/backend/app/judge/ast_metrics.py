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
    """Weighted mean absolute distance from the persona targets, in 0..1.

    The two ratio metrics (docstring, type-hints) are already 0..1 and carry
    equal weight. Function length (``avg_func_lines``) is a real senior-style
    dimension but lives on a much larger scale, so it is normalised against the
    target and folded in with a small weight — enough to reward short, focused
    functions without letting its magnitude dominate. It only contributes when
    present on both sides, so older callers that pass only the two ratios are
    unaffected.
    """
    if not metrics or not persona:
        return 0.0

    parts: list[tuple[float, float]] = []  # (delta, weight)
    for k in ("docstring_ratio", "type_hints_ratio"):
        parts.append((abs(metrics.get(k, 0.0) - persona.get(k, 0.0)), 1.0))

    if "avg_func_lines" in metrics and "avg_func_lines" in persona:
        target = persona.get("avg_func_lines", 0.0)
        delta = abs(metrics.get("avg_func_lines", 0.0) - target)
        norm = min(1.0, delta / target) if target > 0 else 0.0
        parts.append((norm, 0.15))

    total_w = sum(w for _, w in parts)
    if not total_w:
        return 0.0
    return sum(d * w for d, w in parts) / total_w
