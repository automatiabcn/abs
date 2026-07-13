# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""LangFuse client wrapper + @observe decorator.

The runtime singleton wraps `langfuse.Langfuse` when configured; otherwise
falls back to a no-op client so dev/test environments incur zero overhead
and zero network. The `observe` decorator below re-exports the SDK's
decorator with the no-op fallback semantics intact.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "close_langfuse",
    "get_langfuse",
    "is_enabled",
    "observe",
]

_client: Any = None
_real_observe: Callable[..., Any] | None = None


def is_enabled() -> bool:
    return bool(
        getattr(settings, "langfuse_enabled", False)
        and getattr(settings, "langfuse_public_key", "")
        and getattr(settings, "langfuse_secret_key", "")
    )


def get_langfuse() -> Any:
    """Return a configured Langfuse client or None when disabled."""
    global _client
    if _client is not None:
        return _client
    if not is_enabled():
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=getattr(settings, "langfuse_host", "https://langfuse.abs.local"),
        )
        logger.info("langfuse_client_init host=%s", settings.langfuse_host)
    except Exception as exc:  # noqa: BLE001
        logger.warning("langfuse_init_failed: %s", exc)
        _client = None
    return _client


def close_langfuse() -> None:
    global _client
    if _client is None:
        return
    try:
        flush = getattr(_client, "flush", None)
        if callable(flush):
            flush()
    except Exception:  # noqa: BLE001
        logger.exception("langfuse_flush_failed")
    finally:
        _client = None


def _load_real_observe() -> Callable[..., Any] | None:
    global _real_observe
    if _real_observe is not None:
        return _real_observe
    try:
        from langfuse import observe as _impl

        _real_observe = _impl
    except Exception:  # noqa: BLE001
        _real_observe = None
    return _real_observe


def observe(
    *dec_args: Any,
    name: str | None = None,
    capture_input: bool = True,
    capture_output: bool = True,
    **dec_kwargs: Any,
) -> Callable[..., Any]:
    """Drop-in `@observe` that forwards to LangFuse when enabled, no-ops otherwise.

    Both decorator forms are supported: `@observe` and `@observe(name=...)`.
    """

    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        if is_enabled():
            real = _load_real_observe()
            if real is not None:
                kwargs: dict[str, Any] = {
                    "capture_input": capture_input,
                    "capture_output": capture_output,
                }
                if name is not None:
                    kwargs["name"] = name
                kwargs.update(dec_kwargs)
                return real(**kwargs)(fn)

        @functools.wraps(fn)
        def _passthrough(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        return _passthrough

    if dec_args and callable(dec_args[0]) and not name and not dec_kwargs:
        return _wrap(dec_args[0])
    return _wrap
