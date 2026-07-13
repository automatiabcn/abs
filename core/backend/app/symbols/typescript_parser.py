# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""TypeScript / JavaScript symbol parser — regex-based, no tree-sitter.

A tree-sitter binary costs 50+ MB in the image; these patterns are not a full
AST, but hybrid retrieval only needs symbols as a ranking signal, and a partial
hit rate is worth more than the dependency.

Recognised forms:
- `function name(...)` and `async function name(...)`
- `const name = (...) => {}` (arrow function)
- `class Name {` and `class Name extends X {`
- `export { ... } from '...'` and `import ... from '...'`
- `interface Name {` (TS only)
- `type Name = ...` (TS only)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from app.symbols._safe_path import safe_read_text
from app.symbols.parser import Symbol


_RE_FUNCTION = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.MULTILINE
)
_RE_ARROW_FN = re.compile(
    r"^(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s*)?\(",
    re.MULTILINE,
)
_RE_CLASS = re.compile(
    r"^(?:export\s+(?:default\s+)?)?class\s+([A-Za-z_$][\w$]*)", re.MULTILINE
)
_RE_INTERFACE = re.compile(
    r"^(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)", re.MULTILINE
)
_RE_TYPE_ALIAS = re.compile(
    r"^(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=", re.MULTILINE
)
_RE_IMPORT = re.compile(
    r"^import\s+(?:[^'\";]+from\s+)?['\"]([^'\"]+)['\"]", re.MULTILINE
)


def parse_typescript_file(path: Path) -> List[Symbol]:
    """Parse a TS / JS / TSX / JSX file and return the symbols it declares."""
    try:
        text = safe_read_text(path, encoding="utf-8", errors="ignore")
    except (PermissionError, FileNotFoundError, OSError):
        return []
    except Exception:
        return []
    out: List[Symbol] = []
    file_str = str(path)

    def _add(kind: str, name: str, lineno: int) -> None:
        out.append(Symbol(name=name, kind=kind, file=file_str, lineno=lineno))

    def _line_for(span_start: int) -> int:
        return text.count("\n", 0, span_start) + 1

    for m in _RE_FUNCTION.finditer(text):
        _add("function", m.group(1), _line_for(m.start()))
    for m in _RE_ARROW_FN.finditer(text):
        _add("function", m.group(1), _line_for(m.start()))
    for m in _RE_CLASS.finditer(text):
        _add("class", m.group(1), _line_for(m.start()))
    for m in _RE_INTERFACE.finditer(text):
        _add("class", m.group(1), _line_for(m.start()))  # interface ~ class kategorisi
    for m in _RE_TYPE_ALIAS.finditer(text):
        _add("class", m.group(1), _line_for(m.start()))
    for m in _RE_IMPORT.finditer(text):
        _add("import", m.group(1), _line_for(m.start()))

    return out


def is_ts_or_js(path: Path) -> bool:
    return path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
