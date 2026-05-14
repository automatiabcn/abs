# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""012 — First-run redirect middleware.

Setup tamamlanmadiysa whitelist disindaki tum istekler /setup'a yonlendirilir.
Whitelist:
  /healthz
  /v1/setup/*       (setup wizard API)
  /setup            (UI sayfasi)
  /setup/*          (setup assets)
  /setup/assets/*
  /panel/assets/*   (logo + CSS gibi static)
  /static/*
  /_internal/*

Setup tamamlandiktan sonra middleware no-op.
"""

from __future__ import annotations

import json
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse

logger = logging.getLogger(__name__)


_WHITELIST_PREFIXES = (
    "/healthz",
    "/v1/setup",
    "/setup",
    "/panel/assets/",
    "/static/",
    "/_internal/",
    "/mcp",  # Claude Code kurulum oncesi setup_status'u sorgulayabilsin
)


def _setup_completed() -> bool:
    """Setup state file'i her istekte oku — file-stat hizli (<0.1ms)."""
    try:
        from app.api.setup import setup_state_path

        p = setup_state_path()
    except Exception:
        return False
    if not p.is_file():
        return False
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("completed"))
    except Exception:
        return False


class FirstRunMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if _setup_completed():
            return await call_next(request)
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _WHITELIST_PREFIXES):
            return await call_next(request)
        accept = request.headers.get("accept", "")
        # Sprint 2N FAZ F (P2 #2M-001) — API clients asking for JSON get
        # a structured 503 so they can parse `error` + `setup_url`,
        # instead of the HTML wizard redirect that confuses SDK parsers.
        if "application/json" in accept and "text/html" not in accept:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "setup_incomplete",
                    "setup_url": "/setup",
                    "hint": "Visit /setup in a browser to finish first-run setup.",
                },
            )
        if "text/html" in accept:
            return RedirectResponse(url="/setup", status_code=302)
        return RedirectResponse(url="/setup", status_code=307)
