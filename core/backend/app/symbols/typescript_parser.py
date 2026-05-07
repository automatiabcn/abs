# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""022 — TypeScript / JavaScript symbol parser (regex-based, no tree-sitter).

Tree-sitter binary 50+ MB; bunun yerine basit regex pattern'lar ile fonksiyon /
class / variable / import yakalanır. Tam AST değil, %85 hit rate yeterli (016
hybrid retrieval için signal olarak kullanılır).

Desteklenen pattern'lar:
- `function name(...)` veya `async function name(...)`
- `const name = (...) => {}` (arrow function)
- `class Name {` veya `class Name extends X {`
- `export { ... } from '...'` veya `import ... from '...'`
- `interface Name {` (TS only)
- `type Name = ...` (TS only)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

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
    """TS / JS / TSX / JSX dosyasını regex ile parse et, sembolleri döndür."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
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
