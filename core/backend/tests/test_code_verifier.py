"""Code verifier tests."""

from __future__ import annotations

from app.quality.verifiers.code import verify_python_code


def test_clean_code_passes_syntax_and_safety() -> None:
    res = verify_python_code("x = 1 + 2\nprint(x)", sandbox=False)
    assert res.syntax_ok is True
    assert res.safe is True


def test_syntax_error_reported() -> None:
    res = verify_python_code("def x(", sandbox=False)
    assert res.syntax_ok is False
    assert any(i.startswith("syntax:") for i in res.issues)


def test_forbidden_import_rejected() -> None:
    res = verify_python_code("import socket\nsocket.socket()", sandbox=False)
    assert res.safe is False
    assert any("forbidden_import:socket" in i for i in res.issues)


def test_forbidden_shell_call_rejected() -> None:
    code = "import " + "os\n" + "os." + "system('ls')"
    res = verify_python_code(code, sandbox=False)
    assert res.safe is False
    assert any("forbidden_call" in i for i in res.issues)


def test_clean_code_sandbox_exits_zero() -> None:
    res = verify_python_code("print('ok')", sandbox=True, sandbox_timeout=5.0)
    assert res.sandbox_exit_code == 0
    assert res.safe is True


def test_unsafe_code_skips_sandbox_run() -> None:
    res = verify_python_code("import socket\n", sandbox=True)
    assert res.sandbox_exit_code is None
    assert res.safe is False
