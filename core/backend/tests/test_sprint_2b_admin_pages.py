# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Static guard for the 4 admin pages.

These tests don't render React; they only check that the canonical
page files exist on disk (so a future refactor doesn't silently delete
them and ship a 404 onto the sidebar) and that the next.config no
longer redirects the four canonical /admin/* URLs to /panel/*.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LANDING_APP = REPO_ROOT / "core" / "landing" / "app"


def _read(rel: str) -> str:
    return (REPO_ROOT / "core" / "landing" / rel).read_text(encoding="utf-8")


def test_four_new_admin_pages_exist_on_disk():
    for name in ("chat", "mcp-tools", "quota", "dashboard"):
        assert (LANDING_APP / "admin" / name / "page.tsx").is_file(), name


def test_next_config_no_longer_redirects_four_admin_routes():
    cfg = _read("next.config.ts")
    # These four should be REAL routes, not
    # 308 redirects, so the sidebar lands on a real page without losing
    # the URL.
    for source in (
        "/admin/chat",
        "/admin/mcp-tools",
        "/admin/quota",
        "/admin/dashboard",
    ):
        assert f'source: "{source}"' not in cfg, f"unexpected redirect for {source}"


def test_nav_uses_canonical_admin_routes():
    # The nav must advertise the real /admin/* pages rather than the /panel/*
    # URLs they used to 308 to — otherwise every click spends a redirect and the
    # address bar shows a route the product no longer calls canonical.
    #
    # The nav itself moved: the 27-item PanelSidebar became seven domains in
    # components/shell/domains.ts, and its labels are English now. The promise
    # this test was written to protect is about *where the links point*, so it
    # follows the links to their new home rather than dying with the old file.
    nav = _read("components/shell/domains.ts")
    assert 'href: "/admin/dashboard"' in nav
    assert 'href: "/admin/quota"' in nav
    # And it must not have quietly gone back to the legacy targets.
    assert '"/panel/quota"' not in nav.split("REDIRECT_EQUIVALENTS")[0]
