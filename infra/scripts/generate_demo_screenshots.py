"""Demo screenshot generator (Playwright headless).

Usage (requires `pip install playwright && playwright install chromium`):
  python infra/scripts/generate_demo_screenshots.py [--base-url http://localhost:8000]

Captures 8 screens × 2 viewports → 16 PNG files in docs/demo/screenshots/.

Screens captured:
  landing, status, setup_step0, setup_step3, setup_step6, panel,
  connect, privacy, admin, tools

This script is import-safe even when Playwright isn't installed; the
`run()` function imports it lazily.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VIEWPORTS = {
    "desktop": {"width": 1920, "height": 1080},
    "mobile": {"width": 375, "height": 812},
}

# (slug, path) — relative to base URL
SCREENS: list[tuple[str, str]] = [
    ("landing", "/"),
    ("status", "/status"),
    ("setup_step0", "/setup?step=0"),
    ("setup_step3", "/setup?step=3"),
    ("setup_step6", "/setup?step=6"),
    ("panel", "/panel"),
    ("connect", "/panel/connect"),
    ("privacy", "/privacy?lang=en"),
    ("admin", "/admin"),
    ("tools", "/panel/tools.html"),
]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "docs" / "demo" / "screenshots"


def run(base_url: str, out_dir: Path) -> dict:
    """Capture all screen × viewport combinations. Returns a manifest dict."""
    from playwright.sync_api import sync_playwright  # noqa: WPS433 — lazy

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"base_url": base_url, "screenshots": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for viewport_name, vp in VIEWPORTS.items():
                ctx = browser.new_context(viewport=vp, ignore_https_errors=True)
                page = ctx.new_page()
                for slug, path in SCREENS:
                    target = base_url.rstrip("/") + path
                    fname = f"{slug}_{viewport_name}.png"
                    out = out_dir / fname
                    try:
                        page.goto(target, wait_until="networkidle", timeout=15000)
                        page.screenshot(path=str(out), full_page=True)
                        manifest["screenshots"].append(
                            {
                                "slug": slug,
                                "viewport": viewport_name,
                                "url": target,
                                "path": str(out),
                                "ok": True,
                            }
                        )
                    except Exception as exc:
                        manifest["screenshots"].append(
                            {
                                "slug": slug,
                                "viewport": viewport_name,
                                "url": target,
                                "path": str(out),
                                "ok": False,
                                "error": str(exc)[:200],
                            }
                        )
                ctx.close()
        finally:
            browser.close()
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ABS demo screenshot generator")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    try:
        manifest = run(args.base_url, Path(args.out))
    except ImportError as exc:
        print(json.dumps({"ok": False, "error": f"playwright not installed: {exc}"}))
        return 2
    print(json.dumps(manifest, indent=2))
    return 0 if all(s.get("ok") for s in manifest["screenshots"]) else 1


if __name__ == "__main__":
    sys.exit(main())
