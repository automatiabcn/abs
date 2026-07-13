# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""i18n middleware: Accept-Language → request.state.lang.

An explicit `NEXT_LOCALE` cookie wins over the browser header — a language the
user picked outranks the one their browser guesses.
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
