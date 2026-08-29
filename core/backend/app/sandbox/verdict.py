"""Was a failed check the code's fault, or the machine's?

A check that could not even start — the interpreter is a stub, a module the
project depends on is not installed, the runner is missing — says nothing
about the change that was just applied. Reporting it as "FAILED" and
offering "Undo this change" (live, 2026-08-28: `ModuleNotFoundError:
flask_migrate` at collection, exit 2, over a fresh test) points the developer
at their edit when the fix is `pip install`. The 08-28 rule covered the
silent stub (exit 0, no output); this covers the loud one.

Pure: strings in, a one-line reason out, or None when the failure is a real
verdict on the code (assertions, compile errors in the project, exit 1 with
test results).
"""

from __future__ import annotations

import re

__all__ = ["environment_failure"]

_MISSING_MODULE = re.compile(r"(?:ModuleNotFoundError|ImportError): No module named '?([\w.]+)'?")
_NODE_MISSING = re.compile(r"Cannot find module '([^']+)'")
_RESULT_LINE = re.compile(r"\b\d+ (?:passed|failed|error)\b|\bTests?:\s+\d+|\bFAIL\b.*\bPASS\b")


def environment_failure(exit_code: int | None, stdout: str | None, stderr: str | None) -> str | None:
    """A short reason when the check never reached the code; None otherwise."""
    out = (stdout or "") + "\n" + (stderr or "")
    if exit_code == 0:
        return None

    # The runner itself is absent.
    if exit_code == 127 or re.search(r"command not found|not recognized as an internal or external command", out):
        return "the check's command is not installed on this machine"
    if re.search(r"No module named pytest\b|No module named 'pytest'", out):
        return "pytest is not installed in this interpreter"
    if re.search(r"npm ERR! Missing script|npm error Missing script", out):
        return "the npm script the check expected does not exist"

    # pytest could not collect — nothing ran. A missing import at collection
    # is the project's environment, not the edit.
    collection = re.search(r"error(?:s)? during collection|ERROR collecting|Interrupted: ", out)
    missing = _MISSING_MODULE.search(out)
    if missing and (collection or not _RESULT_LINE.search(out)):
        return f"a module the project imports is not installed: {missing.group(1)}"
    if collection and not _RESULT_LINE.search(out):
        return "the tests could not be collected — the project does not import in this interpreter"

    node_missing = _NODE_MISSING.search(out)
    if node_missing and not _RESULT_LINE.search(out):
        return f"a module the project imports is not installed: {node_missing.group(1)}"

    if re.search(r"python3?: (?:can't open file|No such file or directory)|bad interpreter", out):
        return "the interpreter the check uses is missing or broken"

    return None
