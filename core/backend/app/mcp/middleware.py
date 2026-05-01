"""MCP middleware — Mod B (hooks in-process).

Her MCP tool call öncesinde dispatcher.run() çağırır. Hook nudge varsa
tool yanıtının sonuna "\n\n[HOOK] …" olarak eklenir.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable

from app.config import settings
from app.hooks.dispatcher import dispatch_hooks

logger = logging.getLogger(__name__)


def _extract_input_for_hooks(tool_name: str, args: tuple, kwargs: dict) -> dict:
    """MCP tool argümanlarını hook `tool_input` formatına dönüştür.

    Pipeline/basic provider tool'ları `prompt` veya `code`/`text` parametresi alır.
    Bash/Write/Edit olmadığı için tool_input="prompt" yeterli.
    """
    if args:
        prompt_val = args[0]
    else:
        prompt_val = kwargs.get("prompt") or kwargs.get("text") or kwargs.get("code") or ""
    return {"prompt": prompt_val if isinstance(prompt_val, str) else ""}


def _maybe_trigger_first_success(tool_name: str) -> None:
    """019 — Aktif lisans için ilk MCP tool çağrısında first_success email schedule.

    Idempotent: License.first_tool_call_at NOT NULL ise no-op.
    """
    from datetime import datetime, timezone

    if not settings.license_key:
        return  # demo modda lisans yok, skip

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
    """Decorator — MCP tool fonksiyonunu hooks ile sar.

    Kullanım (tools modüllerinde opsiyonel):
        @mcp_server.tool()
        @with_hooks("ask_gptoss")
        async def ask_gptoss(prompt: str) -> str:
            ...
    Mevcut tool'ları değiştirmeden middleware runtime tarafında hooks dispatch
    ile ek context eklemek için alternatif: HTTP middleware (MCP üstünde değil,
    uygulama seviyesinde). FastMCP 1.2 araç-seviyesi middleware'i henüz sabit
    değil; biz dekoratör yöntemini sunuyoruz.
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            # 011 — license/demo gate (mcp_require_license=True olduğunda devreye girer)
            if settings.mcp_require_license:
                try:
                    from app.mcp.gate import _BLOCK_MESSAGE, _gate_status

                    if not _gate_status()["allowed"]:
                        return _BLOCK_MESSAGE
                except Exception as exc:
                    logger.info("gate check skipped: %s", exc)

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

            # 019 — first_success trigger: her başarılı MCP tool çağrısında
            # License.first_tool_call_at IS NULL ise bir kez işaretle ve email schedule.
            try:
                _maybe_trigger_first_success(tool_name)
            except Exception as exc:
                logger.info("first_success trigger skipped: %s", exc)

            if nudge and isinstance(result_text, str):
                return f"{result_text}\n\n[HOOK]\n{nudge}"
            return result_text

        return wrapper

    return decorator
