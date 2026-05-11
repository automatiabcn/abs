# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""URL log sanitizer — strip secret-bearing query params before logging.

Defensive against any HTTP client / formatter that emits request URLs at
INFO level when those URLs carry credentials in query params (Gemini's
historical `?key=`, generic OAuth `?access_token=`, etc.).

The canonical fix is header-auth (see `app.providers.gemini._auth`); this
sanitizer is the second layer so a regression elsewhere can't re-leak.
"""

from __future__ import annotations

import logging
import re

# Match `?key=...` / `&token=...` / `?api_key=...` / `&access_token=...` /
# `?secret=...` / `&auth=...`. Capture the prefix (`?` or `&` + param name +
# `=`) so we can substitute the value while preserving the param name.
_SECRET_PARAM_RX = re.compile(
    r"((?:^|[?&])(?:key|api[_-]?key|token|access[_-]?token|refresh[_-]?token"
    r"|secret|auth|password|client[_-]?secret)=)([^&\s]+)",
    re.IGNORECASE,
)


def sanitize_url_for_log(url: str) -> str:
    """Redact secret-bearing query params in `url`.

    Examples:
        >>> sanitize_url_for_log("https://x/y?key=AIzaSyD123")
        'https://x/y?key=REDACTED'
        >>> sanitize_url_for_log("https://x/y?token=abc&other=keep")
        'https://x/y?token=REDACTED&other=keep'
    """
    if not url or "=" not in url:
        return url
    return _SECRET_PARAM_RX.sub(lambda m: m.group(1) + "REDACTED", url)


class SecretQueryParamFilter(logging.Filter):
    """Logging filter that rewrites any string/URL-bearing log record args.

    Applied at the root or to httpx-related loggers so a stray `client.get(url)`
    that ends up in a log line (via `%s` arg expansion) gets sanitized.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if isinstance(record.msg, str):
            record.msg = sanitize_url_for_log(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    sanitize_url_for_log(a) if isinstance(a, str) else a
                    for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: (sanitize_url_for_log(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
        return True


def install_url_log_sanitizer() -> None:
    """Attach `SecretQueryParamFilter` to httpx + root loggers.

    Idempotent — safe to call multiple times (filter dedup'd by class).
    """
    target_loggers = ("httpx", "httpcore", "uvicorn.access", "")
    flt = SecretQueryParamFilter()
    for name in target_loggers:
        lg = logging.getLogger(name)
        if not any(isinstance(f, SecretQueryParamFilter) for f in lg.filters):
            lg.addFilter(flt)
