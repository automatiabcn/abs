"""023 — i18n middleware: Accept-Language → request.state.lang.

Cookie `NEXT_LOCALE` Accept-Language'i ezer (kullanıcı seçimi öncelikli).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.i18n import detect_lang, SUPPORTED_LANGS, DEFAULT_LANG


class I18nMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cookie_lang = request.cookies.get("NEXT_LOCALE")
        if cookie_lang and cookie_lang.lower() in SUPPORTED_LANGS:
            lang = cookie_lang.lower()
        else:
            lang = detect_lang(request.headers.get("accept-language"))
        request.state.lang = lang or DEFAULT_LANG
        response = await call_next(request)
        return response
