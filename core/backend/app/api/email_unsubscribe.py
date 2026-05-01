"""019 — GET /v1/email/unsubscribe?token=...

JWT verify (license_jti) → email_queue.unsubscribed=True (tüm kindler).
Basit HTML response döner.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.email.scheduler import unsubscribe

router = APIRouter(prefix="/v1/email", tags=["email"])
logger = logging.getLogger(__name__)


_HTML_OK = """<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8"><title>Abonelikten çıkıldı</title></head>
<body style="font-family:system-ui,Arial,sans-serif;max-width:560px;margin:80px auto;padding:24px;color:#1f2937;">
<h1 style="color:#1e57ac;">Çıkış başarılı</h1>
<p>Onboarding email serisinden çıktın. Bundan sonra ABS'ten otomatik onboarding email'i almayacaksın.</p>
<p>Lisans/iade gibi işlemsel email'ler devam edecek.</p>
<p>Hata olduğunu düşünüyorsan: <a href="mailto:support@automatiabcn.com">support@automatiabcn.com</a></p>
</body></html>
"""

_HTML_FAIL = """<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8"><title>Hata</title></head>
<body style="font-family:system-ui,Arial,sans-serif;max-width:560px;margin:80px auto;padding:24px;color:#991b1b;">
<h1>Çıkış işlenemedi</h1>
<p>{reason}</p>
<p>Sorun devam ederse <a href="mailto:support@automatiabcn.com">support@automatiabcn.com</a> ile iletişime geç.</p>
</body></html>
"""


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_endpoint(token: str = Query(..., min_length=10)) -> HTMLResponse:
    ok, info = unsubscribe(token)
    if ok:
        return HTMLResponse(content=_HTML_OK, status_code=200)
    return HTMLResponse(
        content=_HTML_FAIL.format(reason=info or "Geçersiz token"),
        status_code=400,
    )
