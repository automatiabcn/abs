"""Brief 4 R4/R7 — legacy `/panel` is now a redirect to the Next.js
admin under `/admin`. Vanilla-panel HTML widget IDs are no longer
asserted here — that contract moved to the Next.js admin pages and is
covered by Playwright in Brief 4 R7.

Spec: ``_agent-tasks/WORKER_NEXTJS_ADMIN_DEPLOY.md`` §9.
"""

from __future__ import annotations


def test_panel_redirect_to_admin(client):
    """`/panel` → 308 → `/admin` (Next.js admin owns rendering)."""
    r = client.get("/panel", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"] == "/admin"


def test_panel_login_redirect_to_admin(client):
    """`/panel/login` → 308 → `/admin` (Next.js handles login UI)."""
    r = client.get("/panel/login", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["location"] == "/admin"


def test_legacy_panel_returns_410_when_authenticated(client):
    """`/panel/legacy` is the explicit kill switch — admins still see
    a 410 GONE pointing them to /admin/dashboard."""
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200
    g = client.get("/panel/legacy", follow_redirects=False)
    assert g.status_code == 410
    assert "Legacy panel removed" in g.text


def test_legacy_panel_redirects_unauth_to_admin_login(client):
    r = client.get("/panel/legacy", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/admin/login"


def test_admin_route_removed_on_backend(client):
    """Brief 4 R4: backend `/admin` returns 404 — Next.js owns it now.
    Caddy in production routes `/admin/*` to `landing:3000`; the backend
    image must not also serve a vanilla 032 HTML page."""
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 404
