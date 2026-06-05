# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Q12-L25 sweep 3 — request body size cap (DoS mitigation).

Enforces a per-path Content-Length cap **before** FastAPI/Pydantic parses
the body. Without this, a client could ship a 100 MB JSON payload to any
admin endpoint and exhaust memory in the parser pipeline:

* Q12-L25-004 (HIGH DoS) — `/v1/marketplace/install` accepted unbounded
  request bodies. Pydantic Field caps on `plugin_id`/`tenant` (R17) only
  fire **after** the entire body is read into memory.

The cap works on the Content-Length header (the typical attack vector;
streaming bodies without Content-Length are already rejected by Starlette
on chunked-misuse). Per-path caps allow large legitimate uploads on
ingest endpoints while keeping admin endpoints tight.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Mapping

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Per-path-prefix limits in bytes. Longest-prefix match wins; the
# `_default` key supplies the fallback. Tune via settings if tier
# differentiation is needed in future.
DEFAULT_CAPS: Mapping[str, int] = {
    "/v1/rag/ingest-file": 40 * 1024 * 1024,   # 40 MB — raw PDF/DOCX uploads
    "/v1/rag/ingest": 10 * 1024 * 1024,        # 10 MB — JSON text body
    "/v1/marketplace/install": 64 * 1024,      # 64 KB — admin payload
    "/v1/marketplace/uninstall": 16 * 1024,    # 16 KB
    "/v1/workflows/synthesize": 256 * 1024,    # 256 KB
    "/v1/workflows/execute": 1 * 1024 * 1024,  # 1 MB — execute caps in Q12-L25-002
    "/v1/chat/completions": 8 * 1024 * 1024,   # 8 MB — Q12-L25-003 already caps msgs
    "_default": 5 * 1024 * 1024,               # 5 MB — generic admin
    "_hardcap": 50 * 1024 * 1024,              # 50 MB — absolute ceiling
}


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversize requests with HTTP 413 before body parse."""

    def __init__(self, app: Any, caps: Mapping[str, int] | None = None) -> None:
        super().__init__(app)
        self.caps: Mapping[str, int] = dict(caps or DEFAULT_CAPS)

    def _cap_for(self, path: str) -> int:
        # Longest-prefix wins; `_default`/`_hardcap` reserved keys.
        best = self.caps.get("_default", 5 * 1024 * 1024)
        best_len = 0
        for prefix, cap in self.caps.items():
            if prefix.startswith("_"):
                continue
            if path.startswith(prefix) and len(prefix) > best_len:
                best = cap
                best_len = len(prefix)
        hardcap = self.caps.get("_hardcap", 50 * 1024 * 1024)
        return min(best, hardcap)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method.upper()
        if method in {"GET", "HEAD", "OPTIONS", "DELETE"}:
            return await call_next(request)

        cl_raw = request.headers.get("content-length")
        if cl_raw is None:
            # No Content-Length: streamed body. Starlette will surface
            # chunked decoding upstream; we stay out of the way.
            return await call_next(request)
        try:
            content_length = int(cl_raw)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "invalid_content_length"},
            )
        if content_length < 0:
            return JSONResponse(
                status_code=400,
                content={"detail": "invalid_content_length"},
            )

        cap = self._cap_for(request.url.path)
        if content_length > cap:
            logger.warning(
                "body_size_limit_exceeded path=%s cl=%d cap=%d",
                request.url.path,
                content_length,
                cap,
            )
            return JSONResponse(
                status_code=413,
                content={
                    "detail": "request_body_too_large",
                    "limit_bytes": cap,
                    "received_bytes": content_length,
                },
            )
        return await call_next(request)


def install_body_size_limit(app: Any, caps: Mapping[str, int] | None = None) -> None:
    """Wire the middleware into a FastAPI app."""
    app.add_middleware(BodySizeLimitMiddleware, caps=caps)
