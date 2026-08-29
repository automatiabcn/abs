# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Python AST parser.

Fonksiyon (def/async def), class ve import sembollerini cikarir.
Fonksiyon icindeki Call node'lari `edges_out` olarak kaydedilir.
JS/TS parser 017+'ya birakildi.
"""

from __future__ import annotations

import ast
import builtins as _builtins
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Set

_BUILTIN_NAMES = frozenset(dir(_builtins))

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


def parse_python_file(path: Path, *, roots: Optional[Iterable[Path]] = None) -> List[Symbol]:
    """Symbols from one .py file. An unparseable file yields an empty list, not an error."""
    try:
        text = safe_read_text(path, encoding="utf-8", roots=roots)
    except (PermissionError, FileNotFoundError, OSError):
        return []
    except Exception:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    symbols: List[Symbol] = []
    # Already resolved: safe_resolve() ran on the way in, so indexing through
    # a symlinked root still records the real path. Verified rather than
    # assumed — an os.path.realpath() added here changed nothing.
    file_str = str(path)

    class _V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.parent_stack: List[str] = []

        def _full_name(self, leaf: str) -> str:
            return ".".join(self.parent_stack + [leaf])

        def _extract_calls(self, fn_node: ast.AST) -> List[str]:
            """Names this function depends on: what it calls, and what it
            refers to without calling — a parameter that a fixture or
            injector fills (`def test_x(test_client)`), a function passed
            as a value (`on_done=notify`). Blast radius answered 0 for a
            pytest fixture used by five tests because only Call nodes
            counted (live, 2026-08-28, G13). Builtins are dropped; names
            that resolve to no symbol are dropped later by the graph."""
            refs: List[str] = []
            own = getattr(fn_node, "name", None)
            args = getattr(fn_node, "args", None)
            if args is not None:
                for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
                    refs.append(a.arg)
            for n in ast.walk(fn_node):
                if isinstance(n, ast.Call):
                    if isinstance(n.func, ast.Name):
                        refs.append(n.func.id)
                    elif isinstance(n.func, ast.Attribute):
                        refs.append(n.func.attr)
                elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                    refs.append(n.id)
            return [r for r in refs if r not in _BUILTIN_NAMES and r != own and r != "self"]

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


def parse_directory(
    root: Path,
    skip_dirs: Optional[Set[str]] = None,
    *,
    roots: Optional[Iterable[Path]] = None,
    strict: bool = False,
) -> List[Symbol]:
    """Bir dizini recursive tarar, .py dosyalarini parse eder.

    ``roots`` is the allowed-root set the walk is confined to. Left as None it
    is the process-wide ALLOWED_ROOTS (server cwd, /app, /tmp…) — which is the
    right guard for the server's own trees and the wrong one for a customer's
    workspace: every real project lives outside the server's cwd, and until
    2026-08-18 that meant `code_graph_build` returned 0 symbols for every real
    project, silently, while the blast-radius badge stayed "not indexed"
    (found by an audit; every earlier tour had used /tmp projects). Callers
    that already vetted the root pass ``roots=[root]`` so the walk is confined
    to the workspace itself — and symlinks out of it are still refused.

    ``strict`` turns "root not allowed" into a raised PermissionError instead
    of an empty list, so a caller can tell "nothing to parse" from "was not
    allowed to look".
    """
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
    # TS/JS parser dahil
    from app.symbols.typescript_parser import is_ts_or_js, parse_typescript_file

    out: List[Symbol] = []
    root_set = tuple(roots) if roots is not None else None
    try:
        safe_root = safe_resolve(root, roots=root_set)
    except PermissionError:
        if strict:
            raise
        return out
    if not safe_root.exists():
        return out
    if safe_root.is_file():
        if safe_root.suffix == ".py":
            return parse_python_file(safe_root, roots=root_set)
        if is_ts_or_js(safe_root):
            return parse_typescript_file(safe_root, roots=root_set)
        return out
    for dirpath, dirnames, filenames in os.walk(safe_root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                safe_p = safe_resolve(p, roots=root_set)
            except PermissionError:
                continue
            if fn.endswith(".py"):
                out.extend(parse_python_file(safe_p, roots=root_set))
            elif is_ts_or_js(safe_p):
                out.extend(parse_typescript_file(safe_p, roots=root_set))
    return out
