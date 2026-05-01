"""Panel route — auth'lu kullanıcıya static index.html servis eder."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.api.auth import COOKIE_NAME, current_admin

router = APIRouter(tags=["panel"])

PANEL_DIR = Path(__file__).resolve().parents[1] / "static" / "panel"


@router.get("/panel/login")
def panel_login() -> FileResponse:
    """Login sayfası (public)."""
    return FileResponse(PANEL_DIR / "login.html")


@router.get("/panel")
def panel_index(request: Request) -> Response:
    """Ana panel — oturum yoksa login'e yönlendirir."""
    if not request.cookies.get(COOKIE_NAME):
        return RedirectResponse(url="/panel/login", status_code=302)
    # cookie var ama geçersizse yine login'e
    try:
        current_admin(request)
    except Exception:
        return RedirectResponse(url="/panel/login", status_code=302)
    return FileResponse(PANEL_DIR / "index.html")
