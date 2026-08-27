# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Does this proposal leave a template asking for a variable nobody provides?

A recurring incompleteness in Composer output (measured live on a Flask project
2026-08-28): the model edits a template to use a new variable — `{{ page }}`,
`{% if current_year %}` — but does not edit the route to pass it, so applying
the change alone renders a template that raises UndefinedError. The gap is
invisible in the diff: each edit looks fine on its own.

This does not block or repair anything. It attaches a plain-language warning so
the developer sees the missing half instead of a silently-broken partial edit —
the same "make the gap legible" principle the risk badge follows.

The bias is deliberately toward SILENCE. A false "you forgot the route" warning
erodes trust exactly like a false high-risk score, so a variable is flagged
only when it is a bare new identifier the template did not use before, is not a
Jinja/Flask global or a local the template defines, and is passed to that
template by NO render_template call — not in this proposal, not on disk.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Set, Tuple

_TEMPLATE_EXT = (".html", ".htm", ".jinja", ".jinja2", ".j2")

# Names always in scope in a Jinja/Flask template — never a missing route var.
_GLOBALS: frozenset[str] = frozenset(
    {
        "loop", "url_for", "request", "session", "config", "g", "range",
        "dict", "namespace", "cycler", "joiner", "lipsum", "csrf_token",
        "get_flashed_messages", "current_user", "self", "super",
        "true", "false", "none", "True", "False", "None", "and", "or",
        "not", "in", "is", "if", "else", "elif", "for", "endfor", "endif",
        "block", "endblock", "extends", "include", "set", "with", "endwith",
        "macro", "endmacro", "call", "endcall", "filter", "endfilter",
    }
)

_MUSTACHE = re.compile(r"\{\{(.+?)\}\}", re.S)
_STATEMENT = re.compile(r"\{%-?\s*(.+?)\s*-?%\}", re.S)
_IDENT = re.compile(r"[A-Za-z_]\w*")


def _is_template(path: str) -> bool:
    return path.lower().endswith(_TEMPLATE_EXT)


def _added_lines(diff: str) -> List[str]:
    return [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def _value_identifiers(expr: str) -> Set[str]:
    """Identifiers used as VALUES in a Jinja expression.

    An identifier is a value unless it is an attribute (`a.b` → only `a`), a
    call or filter (`f(...)`, `x|filt`), or a keyword-argument name (`k=…`).
    Conservative on purpose: when the role is unclear the identifier is dropped,
    not flagged."""
    # Blank out string literals first, or an identifier inside a quoted argument
    # (url_for('main.home') → 'main') would read as a value.
    expr = re.sub(r"'[^']*'|\"[^\"]*\"", " ", expr)
    out: Set[str] = set()
    for m in _IDENT.finditer(expr):
        i, j = m.start(), m.end()
        prev = expr[i - 1] if i > 0 else ""
        if prev == ".":  # attribute access: the root was already seen
            continue
        nxt = expr[j] if j < len(expr) else ""
        if nxt == "(":  # a function or filter call, not a value
            continue
        # A filter name sits right after a '|' (possibly spaced).
        k = i - 1
        while k >= 0 and expr[k] == " ":
            k -= 1
        if k >= 0 and expr[k] == "|":
            continue
        # A keyword-argument name is `ident =` but not `ident ==`.
        after = expr[j:]
        eq = re.match(r"\s*=(?!=)", after)
        if eq:
            continue
        out.add(m.group(0))
    return out


def _referenced_vars(lines: Iterable[str]) -> Set[str]:
    refs: Set[str] = set()
    for line in lines:
        for m in _MUSTACHE.finditer(line):
            refs |= _value_identifiers(m.group(1))
        for m in _STATEMENT.finditer(line):
            body = m.group(1)
            head = body.split(None, 1)
            if not head:
                continue
            keyword = head[0]
            # Only the control statements that READ a value can dangle.
            if keyword in ("if", "elif"):
                refs |= _value_identifiers(head[1] if len(head) > 1 else "")
            elif keyword == "for":
                # for X[, Y] in EXPR — only EXPR is referenced; X/Y are locals.
                _, _, expr = body.partition(" in ")
                refs |= _value_identifiers(expr)
    return refs


def _template_locals(text: str) -> Set[str]:
    """Names the template itself binds — loop targets, `set`, `with`, macro args
    — which are therefore never a missing route variable."""
    locals_: Set[str] = set()
    for m in _STATEMENT.finditer(text):
        body = m.group(1).strip()
        if body.startswith("for "):
            targets, _, _ = body[4:].partition(" in ")
            locals_ |= set(_IDENT.findall(targets))
        elif body.startswith("set "):
            name = _IDENT.search(body[4:])
            if name:
                locals_.add(name.group(0))
        elif body.startswith("with "):
            for assign in re.finditer(r"([A-Za-z_]\w*)\s*=", body[5:]):
                locals_.add(assign.group(1))
        elif body.startswith("macro "):
            head = body[6:]
            paren = head.find("(")
            if paren != -1:
                inside = head[paren + 1 : head.find(")", paren)]
                locals_ |= set(_IDENT.findall(inside))
    return locals_


_RENDER = re.compile(r"render_template\(\s*['\"]([\w./\-]+)['\"]([^)]*)\)", re.S)
_KWARG = re.compile(r"[,(]\s*([A-Za-z_]\w*)\s*=")


def _rendered_vars_by_template(py_texts: Iterable[str]) -> Dict[str, Set[str]]:
    """Map a template's basename to every variable any render_template passes to
    it, across the given Python sources."""
    out: Dict[str, Set[str]] = {}
    for text in py_texts:
        for m in _RENDER.finditer(text):
            name = os.path.basename(m.group(1))
            kwargs = set(_KWARG.findall("," + m.group(2)))
            out.setdefault(name, set()).update(kwargs)
    return out


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _iter_py_on_disk(workspace_root: str, limit: int = 400) -> Iterable[str]:
    seen = 0
    for dirpath, dirnames, filenames in os.walk(workspace_root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in (".git", "node_modules", ".venv", "venv", "__pycache__", ".idea")
        ]
        for name in filenames:
            if name.endswith(".py"):
                yield _read(os.path.join(dirpath, name))
                seen += 1
                if seen >= limit:
                    return


def coverage_warnings(
    edits: List[Tuple[str, str]],
    workspace_root: str,
) -> List[str]:
    """Warnings for template variables this proposal introduces but no route
    provides. `edits` is a list of (path, unified_diff). Empty when nothing
    dangles — which is the common case and stays silent."""
    template_edits = [(p, d) for p, d in edits if _is_template(p)]
    if not template_edits:
        return []

    # Every render_template in the proposal's own Python edits (added lines)…
    proposal_py_added = [
        "\n".join(_added_lines(d)) for p, d in edits if p.endswith(".py")
    ]
    provided = _rendered_vars_by_template(proposal_py_added)
    # …plus every render_template already in the workspace, so a variable the
    # existing route passes is not reported as missing.
    for name, vars_ in _rendered_vars_by_template(_iter_py_on_disk(workspace_root)).items():
        provided.setdefault(name, set()).update(vars_)

    warnings: List[str] = []
    for path, diff in template_edits:
        base = os.path.basename(path)
        abs_path = (
            path if os.path.isabs(path) else os.path.join(workspace_root, path)
        )
        current = _read(abs_path)
        # Variables the template already referenced through Jinja before this
        # edit — the existing route must already provide them (the template
        # worked before), so they are not the proposal's job to add.
        already_used = _referenced_vars(current.splitlines())
        local = _template_locals(current) | _template_locals("\n".join(_added_lines(diff)))
        provided_here = provided.get(base, set())

        referenced = _referenced_vars(_added_lines(diff))
        dangling = sorted(
            v
            for v in referenced
            if v not in _GLOBALS
            and v not in local
            and v not in provided_here
            and v not in already_used  # genuinely new to this template
        )
        for v in dangling:
            warnings.append(
                f"{path} now uses `{{{{ {v} }}}}` but no route in this proposal "
                f"or in the project passes `{v}` to it — the change may be "
                f"incomplete (the template would raise UndefinedError)."
            )
    return warnings
