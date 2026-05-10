# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Sprint 2B BUG-19/20/25/26 — static guard for the 4 new admin pages.

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
    # Sprint 2B BUG-19/20/25/26 — these four should be REAL routes, not
    # 308 redirects, so the sidebar lands on a real page without losing
    # the URL.
    for source in (
        "/admin/chat",
        "/admin/mcp-tools",
        "/admin/quota",
        "/admin/dashboard",
    ):
        assert (
            f'source: "{source}"' not in cfg
        ), f"unexpected redirect for {source}"


def test_sidebar_uses_canonical_admin_routes():
    sidebar = _read("components/panel/PanelSidebar.tsx")
    # "Genel Bakış" now lands on /admin/dashboard, not /panel.
    assert 'href: "/admin/dashboard", label: "Genel Bakış"' in sidebar
    # "Kota" now lands on /admin/quota, not /panel/quota.
    assert 'href: "/admin/quota", label: "Kota"' in sidebar
