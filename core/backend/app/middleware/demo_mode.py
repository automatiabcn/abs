# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""033 Modul A — Demo Mode response-header middleware.

When ABS_DEMO_MODE is enabled, every response carries an
`X-ABS-Demo-Mode: true` header so the frontend can show the banner
without polling a separate endpoint.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


class DemoModeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if settings.demo_mode:
            response.headers["X-ABS-Demo-Mode"] = "true"
            response.headers["X-ABS-Demo-Seed-Version"] = settings.demo_seed_version
        return response
