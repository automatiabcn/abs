# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""MCP middleware — hooks run in-process, in the same call as the tool.

Hooks dispatch before the tool body; any nudge they produce is appended to the
tool's own reply as a trailing "[HOOK]" block, because MCP gives us no separate
channel to hand the client out-of-band advice.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable

from app.config import settings
from app.hooks.dispatcher import dispatch_hooks

logger = logging.getLogger(__name__)

# Shown when the license gate cannot be evaluated while `mcp_require_license` is
# on. We fail CLOSED there: an error checking the license must never grant
# access to an unlicensed/expired caller.
_GATE_ERROR_MESSAGE = (
    "[LICENSE REQUIRED] License/demo status could not be verified right now, so "
    "the request was refused for safety. Retry shortly, or check your license/"
    "demo at https://abs.automatiabcn.com/"
)


def _extract_input_for_hooks(tool_name: str, args: tuple, kwargs: dict) -> dict:
    """Map MCP tool arguments onto the hook `tool_input` shape.

    Every tool on this surface takes its payload as `prompt` / `text` / `code`;
    there is no Bash/Write/Edit tool here, so hooks only ever need a prompt.
    """
    if args:
        prompt_val = args[0]
    else:
        prompt_val = (
            kwargs.get("prompt") or kwargs.get("text") or kwargs.get("code") or ""
        )
    return {"prompt": prompt_val if isinstance(prompt_val, str) else ""}


def _maybe_trigger_first_success(tool_name: str) -> None:
    """Schedule the onboarding "first success" email on the first tool call.

    Idempotent: a non-NULL License.first_tool_call_at makes this a no-op, so the
    email is queued once per license no matter how often tools are called.
    """
    from datetime import datetime, timezone

    if not settings.license_key:
        return  # demo install — no license row to mark

    try:
        from app.licensing import verify_license

        payload = verify_license(settings.license_key)
    except Exception:
        return

    license_jti = payload.get("jti")
    if not license_jti:
        return

    from sqlmodel import Session, select

    from app.db.models import License
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        lic = db.scalars(select(License).where(License.jti == license_jti)).first()
        if lic is None:
            return
        if lic.first_tool_call_at is not None:
            return  # already triggered
        lic.first_tool_call_at = datetime.now(timezone.utc)
        db.add(lic)
        db.commit()
        # Schedule email
        if lic.customer_email:
            try:
                from app.email.scheduler import schedule_first_success

                schedule_first_success(
                    license_jti=lic.jti,
                    email=lic.customer_email,
                    db=db,
                )
            except Exception as exc:
                logger.info("schedule_first_success failed: %s", exc)


def with_hooks(tool_name: str) -> Callable:
    """Decorator — wrap an MCP tool with the license gate and hook dispatch.

        @mcp_server.tool()
        @with_hooks("ask_gptoss")
        async def ask_gptoss(prompt: str) -> str:
            ...

    FastMCP exposes no stable tool-level middleware API, so the decorator is the
    only place these run per call. Applying it is optional per tool.
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            # License/demo gate — only armed when the operator opts in.
            if settings.mcp_require_license:
                try:
                    from app.mcp.gate import _BLOCK_MESSAGE, _gate_status

                    allowed = _gate_status()["allowed"]
                except Exception as exc:
                    # Fail CLOSED: with require_license on, an error evaluating
                    # the gate must NOT let an unlicensed/expired caller through.
                    logger.warning("license gate errored; failing closed: %s", exc)
                    return _GATE_ERROR_MESSAGE
                if not allowed:
                    return _BLOCK_MESSAGE

            if settings.hooks_enabled and settings.hooks_mode in ("middleware", "both"):
                try:
                    tool_input = _extract_input_for_hooks(tool_name, args, kwargs)
                    result = dispatch_hooks(tool_name, tool_input)
                    nudge = result.get("additional_context", "")
                    deny = result.get("deny_reason")
                    if deny:
                        return f"[HOOK DENY] {deny}"
                except Exception as exc:
                    logger.info("hook middleware failed: %s", exc)
                    nudge = ""
            else:
                nudge = ""

            result_text = await fn(*args, **kwargs)

            # Onboarding milestone: only a call that actually returned counts as
            # the customer's first success, so this runs after the tool body.
            try:
                _maybe_trigger_first_success(tool_name)
            except Exception as exc:
                logger.info("first_success trigger skipped: %s", exc)

            if nudge and isinstance(result_text, str):
                return f"{result_text}\n\n[HOOK]\n{nudge}"
            return result_text

        return wrapper

    return decorator
