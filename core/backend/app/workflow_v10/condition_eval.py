# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Safe boolean evaluation for workflow ``conditional`` nodes.

A condition string is attacker-influenced (it embeds ``{{node}}`` outputs), so
it must NEVER reach :func:`eval`. We render placeholders to quoted string
literals, parse the result with :func:`ast.parse`, then walk a strict
whitelist of node types — comparisons, boolean and/or/not, membership, and
literals only. Anything else (names, calls, attribute/subscript access,
f-strings, comprehensions) raises :class:`ConditionError`.

Supported shapes:
    {{n1}} == "yes"
    {{n1.status}} != "error"
    {{score}} >= 5 and {{ok}} == "true"
    "fail" in {{n1}}
    {{flag}}            # bare truthiness
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict

_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")

_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Constant,
    ast.List,
    ast.Tuple,
)


class ConditionError(ValueError):
    """Raised when a condition is malformed or uses a disallowed construct."""


def _node_text(out: Any) -> str:
    if isinstance(out, dict):
        v = out.get("result")
        if v is not None:
            # bool results render lowercase to match the conditional node's
            # `text` ("true"/"false") and edge labels.
            return str(v).lower() if isinstance(v, bool) else str(v)
        return str(out.get("text") or out.get("error") or out.get("skipped") or "")
    return str(out or "")


def _render_literals(expr: str, outputs: Dict[str, Any]) -> str:
    """Replace each ``{{ref}}`` with a Python string literal of its value.

    Using repr() guarantees the substituted value is an inert literal — it can
    never inject an operator, name or call into the parsed expression.
    """

    def repl(m: "re.Match[str]") -> str:
        key = m.group(1).strip()
        token = key.split(".")[1] if key.startswith("steps.") else key
        token = token.split(".")[0]  # {{n1.status}} → n1
        return repr(_node_text(outputs.get(token, "")))

    return _TEMPLATE_RE.sub(repl, expr)


def _coerce(value: Any) -> Any:
    """Best-effort numeric coercion so ``"5" >= 5`` compares as numbers."""
    if isinstance(value, str):
        s = value.strip()
        try:
            if re.fullmatch(r"-?\d+", s):
                return int(s)
            if re.fullmatch(r"-?\d*\.\d+", s):
                return float(s)
        except ValueError:
            return value
    return value


def _eval(node: ast.AST) -> Any:
    if not isinstance(node, _ALLOWED_NODES):
        raise ConditionError(f"disallowed expression element: {type(node).__name__}")
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e) for e in node.elts]
    if isinstance(node, ast.BoolOp):
        vals = [_eval(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(vals)
        return any(vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval(node.operand)
    if isinstance(node, ast.Compare):
        left = _coerce(_eval(node.left))
        for op, comp in zip(node.ops, node.comparators):
            right = _coerce(_eval(comp))
            if not _apply_op(op, left, right):
                return False
            left = right
        return True
    raise ConditionError(f"disallowed expression element: {type(node).__name__}")


def _apply_op(op: ast.AST, left: Any, right: Any) -> bool:
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.In):
        try:
            return left in right
        except TypeError:
            return False
    if isinstance(op, ast.NotIn):
        try:
            return left not in right
        except TypeError:
            return True
    # ordered comparisons — only valid for same-type operands
    try:
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
    except TypeError:
        return False
    raise ConditionError(f"disallowed operator: {type(op).__name__}")


def evaluate(expr: str, outputs: Dict[str, Any]) -> bool:
    """Render ``{{refs}}`` from *outputs* and safely evaluate *expr* to a bool.

    An empty condition is ``True`` (an unconditional pass-through). A parse or
    whitelist failure raises :class:`ConditionError` — callers treat that as a
    node error rather than silently routing one way.
    """
    expr = (expr or "").strip()
    if not expr:
        return True
    rendered = _render_literals(expr, outputs)
    try:
        tree = ast.parse(rendered, mode="eval")
    except SyntaxError as exc:
        raise ConditionError(f"invalid condition syntax: {exc}") from exc
    return bool(_eval(tree))


__all__ = ["ConditionError", "evaluate"]
