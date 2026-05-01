"""023 Modul F — validate_install.py: 7 categories + fix hints."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script():
    repo = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "validate_install", repo / "infra" / "scripts" / "validate_install.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["validate_install"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_validate_returns_7_categories():
    mod = _load_script()
    out = mod.validate()
    expected = {"python_deps", "playwright", "rag", "git", "mcp", "stripe", "email"}
    assert set(out["results"].keys()) == expected
    assert "summary" in out
    assert "ok" in out


def test_python_deps_check_passes_in_test_env():
    mod = _load_script()
    res = mod._check_python_deps()
    assert res["ok"] is True


def test_mcp_check_returns_ok():
    mod = _load_script()
    res = mod._check_mcp()
    assert res["ok"] is True
    assert res["error"] is None


def test_stripe_check_fails_without_env(monkeypatch):
    mod = _load_script()
    monkeypatch.delenv("ABS_STRIPE_SECRET_KEY", raising=False)
    res = mod._check_stripe()
    assert res["ok"] is False
    assert "ABS_STRIPE_SECRET_KEY" in (res.get("error") or "")
    assert "fix_hint" in res
    assert res["fix_hint"]


def test_email_check_always_ok_via_console_fallback(monkeypatch):
    mod = _load_script()
    monkeypatch.delenv("ABS_SMTP_HOST", raising=False)
    res = mod._check_email()
    assert res["ok"] is True
