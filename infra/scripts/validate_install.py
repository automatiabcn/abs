"""023 — Install validation: 7 categories, fix hint per failure.

Usage:
  python infra/scripts/validate_install.py            # default JSON output
  python infra/scripts/validate_install.py --human    # human-readable table

Output format (JSON):
  {
    "results": {
      "python_deps":  {"ok": bool, "error": str | null, "fix_hint": str | null},
      "playwright":   {...},
      "rag":          {...},
      "git":          {...},
      "mcp":          {...},
      "stripe":       {...},
      "email":        {...}
    },
    "ok": bool,
    "summary": "X/7 OK"
  }

Exit code: 0 if all OK, 1 otherwise.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Callable, Dict


def _check_python_deps() -> Dict[str, Any]:
    required = ["stripe", "sqlmodel", "fastapi", "jwt", "cryptography", "jinja2"]
    missing = []
    for mod in required:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(mod)
    if missing:
        return {
            "ok": False,
            "error": f"Missing Python modules: {', '.join(missing)}",
            "fix_hint": "Run: pip install -e core/backend",
        }
    return {"ok": True, "error": None, "fix_hint": None}


def _check_playwright() -> Dict[str, Any]:
    if not shutil.which("npx"):
        return {
            "ok": False,
            "error": "npx not found",
            "fix_hint": "Install Node.js (https://nodejs.org/)",
        }
    # Check Playwright cache directory
    candidates = [
        os.path.expanduser("~/Library/Caches/ms-playwright"),
        os.path.expanduser("~/.cache/ms-playwright"),
    ]
    for c in candidates:
        if os.path.isdir(c) and os.listdir(c):
            return {"ok": True, "error": None, "fix_hint": None}
    return {
        "ok": False,
        "error": "Playwright browsers not installed",
        "fix_hint": "Run: npx playwright install",
    }


def _check_rag() -> Dict[str, Any]:
    try:
        importlib.import_module("chromadb")
    except Exception as exc:
        return {
            "ok": False,
            "error": f"chromadb import failed: {exc}",
            "fix_hint": "Run: pip install chromadb",
        }
    return {"ok": True, "error": None, "fix_hint": None}


def _check_git() -> Dict[str, Any]:
    if not shutil.which("git"):
        return {
            "ok": False,
            "error": "git binary not found",
            "fix_hint": "Install Git (https://git-scm.com/downloads)",
        }
    try:
        name = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        email = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception as exc:
        return {
            "ok": False,
            "error": f"git config failed: {exc}",
            "fix_hint": "Run: git config --global user.name '...' && git config --global user.email '...'",
        }
    if not name or not email:
        return {
            "ok": False,
            "error": "git user.name or user.email empty",
            "fix_hint": "Run: git config --global user.name '...' && git config --global user.email '...'",
        }
    return {"ok": True, "error": None, "fix_hint": None}


def _check_mcp() -> Dict[str, Any]:
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(repo, "core", "backend"))
    try:
        from app.mcp.server import _REGISTERED_COUNT  # type: ignore
    except Exception as exc:
        return {
            "ok": False,
            "error": f"MCP server import failed: {exc}",
            "fix_hint": "Check core/backend/app/mcp/server.py imports",
        }
    if _REGISTERED_COUNT < 100:
        return {
            "ok": False,
            "error": f"MCP tool count low: {_REGISTERED_COUNT}",
            "fix_hint": "Reinstall: pip install -e core/backend",
        }
    return {"ok": True, "error": None, "fix_hint": None}


def _check_stripe() -> Dict[str, Any]:
    # Honour the billing kill-switch the landing image
    # already wires through `NEXT_PUBLIC_BILLING_ENABLED`. Self-host
    # customers who don't resell ABS opt out by setting
    # `ABS_BILLING_ENABLED=false`; the validator then reports OK with a
    # skipped-hint so 7/7 doesn't require a Stripe account just to boot.
    # Backwards compatible: missing env var keeps the original FAIL
    # behaviour the pilot playbook documents.
    billing_enabled = os.environ.get("ABS_BILLING_ENABLED", "true").strip().lower()
    if billing_enabled in ("false", "0", "no", "off"):
        return {
            "ok": True,
            "error": None,
            "fix_hint": (
                "Billing kill-switch active (ABS_BILLING_ENABLED=false). "
                "Set a Stripe key only if you intend to resell ABS."
            ),
        }
    if not os.environ.get("ABS_STRIPE_SECRET_KEY"):
        return {
            "ok": False,
            "error": "ABS_STRIPE_SECRET_KEY not set",
            "fix_hint": (
                "Set ABS_STRIPE_SECRET_KEY in .env, or "
                "ABS_BILLING_ENABLED=false if you don't resell ABS."
            ),
        }
    return {"ok": True, "error": None, "fix_hint": None}


def _check_email() -> Dict[str, Any]:
    # SMTP_HOST set => real transport; otherwise console fallback (also OK)
    if os.environ.get("ABS_SMTP_HOST"):
        return {"ok": True, "error": None, "fix_hint": None}
    return {
        "ok": True,
        "error": None,
        "fix_hint": "Console fallback active (set ABS_SMTP_HOST for real email)",
    }


_CHECKS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "python_deps": _check_python_deps,
    "playwright": _check_playwright,
    "rag": _check_rag,
    "git": _check_git,
    "mcp": _check_mcp,
    "stripe": _check_stripe,
    "email": _check_email,
}


def validate() -> Dict[str, Any]:
    results: Dict[str, Dict[str, Any]] = {}
    ok_count = 0
    for name, fn in _CHECKS.items():
        try:
            res = fn()
        except Exception as exc:
            res = {
                "ok": False,
                "error": f"check raised: {exc}",
                "fix_hint": None,
            }
        results[name] = res
        if res.get("ok"):
            ok_count += 1
    return {
        "results": results,
        "ok": ok_count == len(_CHECKS),
        "summary": f"{ok_count}/{len(_CHECKS)} OK",
    }


def _human_print(out: Dict[str, Any]) -> None:
    print(f"ABS install validation — {out['summary']}")
    print("-" * 50)
    for name, res in out["results"].items():
        status = "OK  " if res["ok"] else "FAIL"
        print(f"  [{status}] {name}")
        if res.get("error"):
            print(f"         error: {res['error']}")
        if res.get("fix_hint"):
            print(f"         hint:  {res['fix_hint']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ABS install validator")
    parser.add_argument("--human", action="store_true", help="Human-readable output")
    args = parser.parse_args(argv)

    out = validate()
    if args.human:
        _human_print(out)
    else:
        print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
