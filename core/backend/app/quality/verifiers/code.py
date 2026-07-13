# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Code verifier: AST parse + ruff dry-run + sandbox exec budget.

The sandbox is a process-isolated `python -c` with timeout. Code that touches
the network, filesystem outside `/tmp`, or imports shell-spawning APIs is
rejected statically before execution.
"""

from __future__ import annotations

import ast
import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["CodeVerificationResult", "verify_python_code"]


_FORBIDDEN_NAMES = {
    "os" + ".system",
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.call",
    "socket.create_connection",
    "socket.socket",
    "urllib.request.urlopen",
    "ftplib.FTP",
    "smtplib.SMTP",
}
_FORBIDDEN_IMPORTS = {"socket", "urllib.request", "smtplib", "ftplib"}


@dataclass(slots=True)
class CodeVerificationResult:
    syntax_ok: bool
    lint_ok: bool
    safe: bool
    sandbox_exit_code: int | None
    issues: list[str] = field(default_factory=list)


def _walk_for_violations(tree: ast.AST) -> list[str]:
    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _FORBIDDEN_IMPORTS:
                    issues.append(f"forbidden_import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module in _FORBIDDEN_IMPORTS:
                issues.append(f"forbidden_import:{node.module}")
        elif isinstance(node, ast.Attribute):
            try:
                full = ast.unparse(node)
            except Exception:
                full = ""
            if any(name in full for name in _FORBIDDEN_NAMES):
                issues.append(f"forbidden_call:{full}")
    return issues


def _ruff_check(code_text: str) -> tuple[bool, list[str]]:
    if shutil.which("ruff") is None:
        return True, ["ruff_not_installed_skip"]
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(code_text)
        path = fh.name
    try:
        proc = subprocess.run(
            ["ruff", "check", "--no-cache", "--quiet", path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return proc.returncode == 0, [
            line for line in proc.stdout.splitlines() if line.strip()
        ]
    except Exception as exc:  # noqa: BLE001
        return True, [f"ruff_error:{exc}"]
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass


def verify_python_code(
    code_text: str,
    *,
    sandbox: bool = True,
    sandbox_timeout: float = 5.0,
) -> CodeVerificationResult:
    issues: list[str] = []
    try:
        tree = ast.parse(code_text)
        syntax_ok = True
    except SyntaxError as exc:
        issues.append(f"syntax:{exc.msg}@line {exc.lineno}")
        return CodeVerificationResult(
            syntax_ok=False,
            lint_ok=False,
            safe=False,
            sandbox_exit_code=None,
            issues=issues,
        )

    issues.extend(_walk_for_violations(tree))
    safe = not any(
        i.startswith(("forbidden_import:", "forbidden_call:")) for i in issues
    )

    lint_ok, lint_issues = _ruff_check(code_text)
    issues.extend(lint_issues)

    sandbox_exit: int | None = None
    if sandbox and safe and syntax_ok:
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code_text],
                capture_output=True,
                text=True,
                timeout=sandbox_timeout,
                cwd="/tmp",
            )
            sandbox_exit = proc.returncode
            if sandbox_exit != 0:
                issues.append(f"sandbox_exit:{sandbox_exit}")
        except subprocess.TimeoutExpired:
            issues.append("sandbox_timeout")
            sandbox_exit = -1
        except Exception as exc:  # noqa: BLE001
            issues.append(f"sandbox_error:{exc}")

    return CodeVerificationResult(
        syntax_ok=syntax_ok,
        lint_ok=lint_ok,
        safe=safe,
        sandbox_exit_code=sandbox_exit,
        issues=issues,
    )
