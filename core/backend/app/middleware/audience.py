# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-058 — X-ABS-Audience header enforcement (caveat #11)."""

from __future__ import annotations

from typing import Any, Callable, Awaitable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.auth.oauth.server import verify_access_token


class AudienceEnforcerMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Any,
        expected_audience: str,
        enforce: bool = True,
        protected_path_prefix: str = "/v1/",
    ) -> None:
        super().__init__(app)
        self.expected_audience = expected_audience
        self.enforce = enforce
        self.protected_path_prefix = protected_path_prefix

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self.enforce:
            return await call_next(request)
        if not request.url.path.startswith(self.protected_path_prefix):
            return await call_next(request)

        header_audience = request.headers.get("X-ABS-Audience")
        if header_audience != self.expected_audience:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "missing or invalid X-ABS-Audience header",
                    "expected": self.expected_audience,
                },
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "missing authorization"},
            )
        token = auth_header[7:]
        try:
            verify_access_token(token, audience=self.expected_audience)
        except Exception:
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid token or audience mismatch"},
            )
        return await call_next(request)


def install_audience_enforcer(app: Any, settings: Any) -> None:
    enforce = bool(getattr(settings, "audience_enforce", False))
    value = str(getattr(settings, "audience_value", "abs-mcp"))
    if enforce:
        app.add_middleware(
            AudienceEnforcerMiddleware,
            expected_audience=value,
            enforce=True,
        )
