# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""016 — Python AST parser.

Fonksiyon (def/async def), class ve import sembollerini cikarir.
Fonksiyon icindeki Call node'lari `edges_out` olarak kaydedilir.
JS/TS parser 017+'ya birakildi.
"""

from __future__ import annotations

import ast
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from app.symbols._safe_path import safe_read_text, safe_resolve

logger = logging.getLogger(__name__)


@dataclass
class Symbol:
    name: str
    kind: str  # function | class | import
    file: str
    lineno: int
    parent: Optional[str] = None
    edges_out: List[str] = field(default_factory=list)


def parse_python_file(path: Path) -> List[Symbol]:
    """Tek bir .py dosyasindan sembolleri cikar. Hata durumunda bos liste."""
    try:
        text = safe_read_text(path, encoding="utf-8")
    except (PermissionError, FileNotFoundError, OSError):
        return []
    except Exception:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    symbols: List[Symbol] = []
    file_str = str(path)

    class _V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.parent_stack: List[str] = []

        def _full_name(self, leaf: str) -> str:
            return ".".join(self.parent_stack + [leaf])

        def _extract_calls(self, fn_node: ast.AST) -> List[str]:
            calls: List[str] = []
            for n in ast.walk(fn_node):
                if isinstance(n, ast.Call):
                    if isinstance(n.func, ast.Name):
                        calls.append(n.func.id)
                    elif isinstance(n.func, ast.Attribute):
                        calls.append(n.func.attr)
            return calls

        def _emit_function(self, node: ast.AST, name: str) -> None:
            full = self._full_name(name)
            sym = Symbol(
                name=full,
                kind="function",
                file=file_str,
                lineno=getattr(node, "lineno", 0),
                parent=".".join(self.parent_stack) or None,
            )
            sym.edges_out = sorted(set(self._extract_calls(node)))
            symbols.append(sym)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # type: ignore[override]
            self._emit_function(node, node.name)
            self.parent_stack.append(node.name)
            self.generic_visit(node)
            self.parent_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # type: ignore[override]
            self._emit_function(node, node.name)
            self.parent_stack.append(node.name)
            self.generic_visit(node)
            self.parent_stack.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # type: ignore[override]
            full = self._full_name(node.name)
            symbols.append(
                Symbol(
                    name=full,
                    kind="class",
                    file=file_str,
                    lineno=node.lineno,
                    parent=".".join(self.parent_stack) or None,
                )
            )
            self.parent_stack.append(node.name)
            self.generic_visit(node)
            self.parent_stack.pop()

        def visit_Import(self, node: ast.Import) -> None:  # type: ignore[override]
            for alias in node.names:
                symbols.append(
                    Symbol(
                        name=alias.name,
                        kind="import",
                        file=file_str,
                        lineno=node.lineno,
                    )
                )

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # type: ignore[override]
            mod = node.module or ""
            for alias in node.names:
                full = f"{mod}.{alias.name}" if mod else alias.name
                symbols.append(
                    Symbol(
                        name=full,
                        kind="import",
                        file=file_str,
                        lineno=node.lineno,
                    )
                )

    _V().visit(tree)
    return symbols


def parse_directory(root: Path, skip_dirs: Optional[Set[str]] = None) -> List[Symbol]:
    """Bir dizini recursive tarar, .py dosyalarini parse eder."""
    skip = skip_dirs or {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".pytest_cache",
        ".cache",
    }
    # 022 — TS/JS parser dahil
    from app.symbols.typescript_parser import is_ts_or_js, parse_typescript_file

    out: List[Symbol] = []
    try:
        safe_root = safe_resolve(root)
    except PermissionError:
        return out
    if not safe_root.exists():
        return out
    if safe_root.is_file():
        if safe_root.suffix == ".py":
            return parse_python_file(safe_root)
        if is_ts_or_js(safe_root):
            return parse_typescript_file(safe_root)
        return out
    for dirpath, dirnames, filenames in os.walk(safe_root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                safe_p = safe_resolve(p)
            except PermissionError:
                continue
            if fn.endswith(".py"):
                out.extend(parse_python_file(safe_p))
            elif is_ts_or_js(safe_p):
                out.extend(parse_typescript_file(safe_p))
    return out
