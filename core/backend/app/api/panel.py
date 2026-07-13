# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Panel route — legacy `/panel` deprecated 2026-05-07.

The legacy monolithic HTML panel is not shipped. The only frontend is the
Next.js admin under `/admin/*`, so this module exists purely for backwards
compatibility: it redirects the login page to `/admin/login` and the panel
index to `/admin/dashboard`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.api.auth import COOKIE_NAME, current_admin

router = APIRouter(tags=["panel"])

PANEL_DIR = Path(__file__).resolve().parents[1] / "static" / "panel"


@router.get("/panel/login")
def panel_login() -> Response:
    """Legacy login → /admin redirect (Next.js handles routing)."""
    return RedirectResponse(url="/admin", status_code=308)


@router.get("/panel")
def panel_index(request: Request) -> Response:
    """Legacy panel → /admin redirect. The target enforces the session cookie;
    this handler deliberately does not."""
    return RedirectResponse(url="/admin", status_code=308)


# Kept so old links to the removed panel/index.html (e.g. an embedded iframe)
# Get an explicit "gone" signal instead of a bare 404.
@router.get("/panel/legacy")
def panel_legacy_disabled(request: Request) -> Response:
    """Legacy panel index — disabled, answers 410 GONE."""
    if not request.cookies.get(COOKIE_NAME):
        return RedirectResponse(url="/admin/login", status_code=302)
    try:
        current_admin(request)
    except Exception:
        return RedirectResponse(url="/admin/login", status_code=302)
    # Authenticated admins are refused too: the page is gone, not protected.
    return Response(
        content=(
            "Legacy panel removed. Use /admin/dashboard "
            "(Automatia ABS Next.js admin)."
        ),
        status_code=410,
        media_type="text/plain",
    )


# Catch-all, so that any legacy `/panel/<x>` link redirects instead of 404ing:
# Only `/panel`, `/panel/login` and `/panel/legacy` have explicit handlers.
#
# `/panel/assets/*` must be excluded. main.py mounts StaticFiles AFTER this
# Router, but Starlette matches routes in declaration order, so the catch-all
# Would shadow the mount. Once a request matches here the router chain stops,
# so an asset path cannot be handed on to the mount — it has to be served
# Directly with FileResponse rather than 404ed.
@router.get("/panel/{path:path}")
def panel_subpath_compat_redirect(path: str) -> Response:
    """Legacy `/panel/<x>` → `/admin/<x>` 308 redirect.

    `/panel/assets/*` is served from the static panel directory instead of
    being redirected.
    """
    if path.startswith("assets/"):
        asset_path = PANEL_DIR / path
        if asset_path.is_file():
            return FileResponse(str(asset_path))
        return Response(status_code=404)
    target = f"/admin/{path}" if path else "/admin"
    return RedirectResponse(url=target, status_code=308)
