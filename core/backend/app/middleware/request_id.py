# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""RequestIDMiddleware: per-request correlation ID.

Reads the `X-Request-ID` request header (or generates a UUID4 hex token
when absent) and stores it on `request.state.request_id`. Echoes the
same value on the response header so that an upstream proxy / browser /
log aggregator can correlate a single request across nginx → backend →
downstream cerbos / qdrant / DB.

Mounted as the OUTERMOST middleware so every other middleware and every
audit log emitted via `app.observability.audit.emit_event` sees the
correlation ID.
"""

from __future__ import annotations

import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
_MAX_HEADER_LEN = 128
_ALLOWED = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_")


def _safe(candidate: str | None) -> str | None:
    if not candidate:
        return None
    if len(candidate) > _MAX_HEADER_LEN:
        return None
    if not all(ch in _ALLOWED for ch in candidate):
        return None
    return candidate


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = _safe(request.headers.get(REQUEST_ID_HEADER))
        request_id = incoming or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
