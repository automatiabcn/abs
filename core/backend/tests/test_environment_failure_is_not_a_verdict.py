"""A check that never reached the code is not a verdict on the code.

Live, 2026-08-28: Approve ran `python3 -m pytest -q` over a project whose
.venv was a stub; pytest died at collection with `ModuleNotFoundError:
flask_migrate`, exit 2. The panel said FAILED and offered "Undo this change".
The change was fine; the machine was not. `sandbox_run` now names that
(`environment`) and marks the run inconclusive, so the panel says
"unverified — <why>" and does not point at the edit.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.sandbox.verdict import environment_failure

COLLECTION_ERROR = """\
==================================== ERRORS ====================================
_________________ ERROR collecting tests/test_market.py _________________
ImportError while importing test module '/w/tests/test_market.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
tests/test_market.py:2: in <module>
    from app import create_app, db
app/__init__.py:3: in <module>
    from flask_migrate import Migrate
E   ModuleNotFoundError: No module named 'flask_migrate'
=========================== short test summary info ============================
ERROR tests/test_market.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.27s
"""

REAL_FAILURE = """\
F.                                                                       [100%]
=================================== FAILURES ===================================
____________________________ test_market_no_results ____________________________
    assert b'Robot A' not in response.data
E   AssertionError
1 failed, 1 passed in 0.31s
"""


@pytest.mark.parametrize(
    "code,out,expect",
    [
        (2, COLLECTION_ERROR, "flask_migrate"),
        (1, "Traceback...\nModuleNotFoundError: No module named 'sqlalchemy'\n", "sqlalchemy"),
        (127, "bash: pytest: command not found\n", "not installed"),
        (1, "/usr/bin/python3: No module named pytest\n", "pytest is not installed"),
        (1, "Error: Cannot find module 'vitest'\n", "vitest"),
        (126, "bash: .venv/bin/python: bad interpreter: No such file or directory\n", "interpreter"),
    ],
)
def test_environment_failures_are_named(code, out, expect):
    why = environment_failure(code, out, "")
    assert why is not None and expect in why


@pytest.mark.parametrize(
    "code,out",
    [
        (1, REAL_FAILURE),
        (1, "SyntaxError: invalid syntax\n  File \"app/routes.py\", line 12\n"),
        (0, ""),
        (0, "3 passed in 0.4s"),
        # a missing module *inside a test that ran* is the code's problem, not collection
        (1, "F\nE   ModuleNotFoundError: No module named 'nope'\n1 failed, 2 passed in 0.2s\n"),
    ],
)
def test_real_verdicts_are_left_alone(code, out):
    assert environment_failure(code, out, "") is None


def _res(**over):
    base = dict(
        ok=False, exit_code=2, stdout=COLLECTION_ERROR, stderr="", mechanism="seatbelt",
        duration_ms=5, refused=None, truncated=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_sandbox_run_marks_environment_failure_inconclusive(monkeypatch, tmp_path):
    import app.mcp.server  # noqa: F401 — circular import guard
    from app.mcp.tools import sandbox_tools as st

    monkeypatch.setattr(st._sandbox, "run", lambda *a, **k: _res(), raising=True)
    out = json.loads(await st.sandbox_run("python3 -m pytest -q", workspace_root=str(tmp_path)))
    if out.get("refused"):
        pytest.skip(f"sandbox refused in this environment: {out['refused']}")
    assert out["ok"] is False
    assert out["inconclusive"] is True
    assert "flask_migrate" in out["environment"]

    monkeypatch.setattr(st._sandbox, "run", lambda *a, **k: _res(exit_code=1, stdout=REAL_FAILURE), raising=True)
    out = json.loads(await st.sandbox_run("python3 -m pytest -q", workspace_root=str(tmp_path)))
    if not out.get("refused"):
        assert out["inconclusive"] is False
        assert out["environment"] is None
