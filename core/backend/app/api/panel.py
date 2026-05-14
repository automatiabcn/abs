# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Panel route — legacy `/panel` deprecated 2026-05-07.

Founder kararı: legacy ABS HTML panel (Cosmos balls + monolithic
index.html) müşteriye gitmiyor. Tek frontend = Next.js admin under
`/admin/*`. Bu modül artık sadece geriye dönük uyumluluk için redirect
sağlar; login sayfası `/admin/login`'a, panel ana sayfası
`/admin/dashboard`'a yönlendirilir.
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
    """Legacy panel → /admin redirect (Next.js admin once deployed).

    Cookie kontrolü hedef tarafta yapılır.
    """
    return RedirectResponse(url="/admin", status_code=308)


# Tek-seferlik fallback: hâlâ eski panel/index.html'i serve eden
# legacy linkler (örn. embed iframe) için DEPRECATED hint döndür.
@router.get("/panel/legacy")
def panel_legacy_disabled(request: Request) -> Response:
    """Legacy panel index — disabled. Müşteri delivery için 410 GONE."""
    if not request.cookies.get(COOKIE_NAME):
        return RedirectResponse(url="/admin/login", status_code=302)
    try:
        current_admin(request)
    except Exception:
        return RedirectResponse(url="/admin/login", status_code=302)
    # Kullanıcı admin olsa bile artık sunulmuyor — bilinçli fail.
    return Response(
        content=(
            "Legacy panel removed. Use /admin/dashboard "
            "(Automatia ABS Next.js admin)."
        ),
        status_code=410,
        media_type="text/plain",
    )


# Sprint 2N FAZ E (P1 #2M-009) — catch-all `/panel/{path}` → `/admin/{path}`.
# Brief'in `/panel/quota`, `/panel/tools`, `/panel/chat`, `/panel/meetings`
# çağrıları Sprint 2M sırasında 404 dönüyordu çünkü yalnızca `/panel`,
# `/panel/login` ve `/panel/legacy` redirect handler'ları kayıtlı.
#
# `/panel/assets/*` (StaticFiles mount'u tarafından serve edilir) exclude
# edilir — main.py panel_router include'undan SONRA StaticFiles mount eder,
# ama Starlette route order'ı declaration'a göredir, bu yüzden burada
# exclude etmeliyiz. `assets/` prefix'li path'ler 404'e düşerse Starlette
# router zinciri devam edemez; bu nedenle 404 yerine doğrudan static
# dosyayı serve eden FileResponse döner. Bu sayede main.py mount'una
# bağlı kalmadan catch-all + static dosya servisi birlikte çalışır.
@router.get("/panel/{path:path}")
def panel_subpath_compat_redirect(path: str) -> Response:
    """Legacy `/panel/<x>` → `/admin/<x>` 308 redirect.

    `/panel/assets/*` istekleri StaticFiles dosyalarına yönlendirilir,
    redirect uygulanmaz.
    """
    if path.startswith("assets/"):
        asset_path = PANEL_DIR / path
        if asset_path.is_file():
            return FileResponse(str(asset_path))
        return Response(status_code=404)
    target = f"/admin/{path}" if path else "/admin"
    return RedirectResponse(url=target, status_code=308)
