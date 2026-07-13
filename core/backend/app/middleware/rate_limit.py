# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Rate limiting via slowapi.

Default in-memory (single-instance). Multi-instance deployments should set
`ABS_RATE_LIMIT_STORAGE_URI` to a Redis URI (e.g. `redis://host:6379/0`).

Public API:
  - `limiter` — singleton Limiter, decorate routes with `@limiter.limit(...)`.
  - `install_rate_limit(app)` — registers Starlette middleware + 429 handler.
  - `record_breach()` — bookkeeping for `security_audit` MCP tool.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


_breach_lock = threading.Lock()
_breach_timestamps: list[float] = []


def record_breach() -> None:
    """Record a 429 timestamp for security_audit reporting."""
    now = datetime.now(timezone.utc).timestamp()
    with _breach_lock:
        _breach_timestamps.append(now)
        # Keep only last 24h
        cutoff = now - 24 * 3600
        _breach_timestamps[:] = [t for t in _breach_timestamps if t >= cutoff]


def breach_count_24h() -> int:
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - 24 * 3600
    with _breach_lock:
        return sum(1 for t in _breach_timestamps if t >= cutoff)


def _trusted_proxy_set() -> frozenset[str]:
    raw = getattr(settings, "trusted_proxies", "") or ""
    return frozenset(
        ip.strip() for ip in raw.split(",") if ip.strip()
    )


def client_ip_for_rate_limit(request: Request) -> str:
    """Sprint 2I UAT-042 — pick the real client IP for rate-limit keying.

    If the immediate hop (``request.client.host``) is listed in
    ``ABS_TRUSTED_PROXIES`` we honour the first IP in
    ``X-Forwarded-For``. Untrusted hops fall back to the raw socket
    address so a malicious origin cannot spoof its IP by setting the
    header itself.
    """
    remote = get_remote_address(request)
    if remote in _trusted_proxy_set():
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            first = fwd.split(",", 1)[0].strip()
            if first:
                return first
    return remote


limiter = Limiter(
    key_func=client_ip_for_rate_limit,
    storage_uri=settings.rate_limit_storage_uri,
    default_limits=[],  # opt-in per route via decorator
)


async def _rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    record_breach()
    retry_after: Optional[int] = None
    try:
        # slowapi 0.1.x: exc.detail is "X per minute" — extract seconds
        # Fallback: 60 seconds
        retry_after = 60
    except Exception:
        retry_after = 60
    response = JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Try again later.",
            "limit": str(exc.detail) if hasattr(exc, "detail") else "unknown",
        },
    )
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
    logger.warning(
        "[rate-limit] 429 path=%s ip=%s",
        request.url.path,
        get_remote_address(request),
    )
    return response


def install_rate_limit(app) -> None:
    """Install limiter into FastAPI app. No-op if rate_limit_enabled=False."""
    if not settings.rate_limit_enabled:
        logger.info("[rate-limit] disabled via settings.rate_limit_enabled")
        return
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
