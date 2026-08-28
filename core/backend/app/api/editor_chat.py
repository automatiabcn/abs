# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The editor chat, streamed.

`cascade_ask` answers in one piece: the developer looks at "Thinking…" for
as long as the provider takes and then reads a finished answer. This route
is the same question — the same chain, the same project files, the same
voice, decided by the same code (`prepare_chat_ask`) — delivered as the
provider produces it, with a way to stop.

Server-sent events, one JSON object per ``data:`` line:

    meta      {used_files, chain}            — before any provider is called
    provider  {name, streams, cached?}       — a leg starts
    delta     {text}                         — a piece of the answer
    done      {provider, model, tokens_in, tokens_out, elapsed_ms, cost_usd,
               cached, truncated, providers_tried}
    error     {error, detail, partial?, providers_tried?}

It is guarded like the MCP transport it stands beside: the editor's
``abs_mcp_`` bearer token, the same scope rule, the same licence gate. It
does not open a new way in.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/editor/chat", tags=["editor-chat"])


class StreamChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=60_000)
    history: str = ""
    style: str = "chat"
    prefer: str = ""
    workspace_root: str = ""
    client_id: str = ""
    max_tokens: int = Field(default=1400, ge=16, le=8000)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    use_cache: bool = True


def _sse(obj: Dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _bearer(request: Request) -> Dict[str, Any]:
    """The editor's token, checked the way the MCP transport checks it."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Send the editor token as 'Authorization: Bearer abs_mcp_...'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth[7:].strip()
    from app.api.mcp_tokens import verify_token

    payload = verify_token(token)
    tok_scope = str(payload.get("scope", "all"))
    if tok_scope not in ("mcp", "all"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"scope_not_allowed:{tok_scope}"
        )
    return payload


def _licence_allows() -> Optional[str]:
    """The MCP surface's own gate, asked the same question. Returns the
    refusal text, or None when the request may run."""
    from app.mcp.gate import _gate_status

    st = _gate_status()
    if st.get("allowed"):
        return None
    return st.get("detail") or "This ABS server is not on an active subscription."


@router.post("/stream")
async def stream_chat(body: StreamChatRequest, request: Request) -> StreamingResponse:
    payload = _bearer(request)
    refused = _licence_allows()
    if refused:
        # The tool surface says this in-band; so does the stream, so the
        # panel can show the same words instead of a bare status code.
        async def _refuse() -> AsyncIterator[str]:
            yield _sse({"type": "error", "error": "subscription_required", "detail": refused})

        return StreamingResponse(_refuse(), media_type="text/event-stream")

    from app.mcp.context import set_mcp_caller

    set_mcp_caller(payload.get("tenant"), payload.get("actor"))
    tenant = str(payload.get("tenant") or "").strip() or None

    async def _events() -> AsyncIterator[str]:
        from app.cascade.orchestrator import stream_with_cascade
        from app.db.session import current_tenant
        from app.mcp.tools.engine_panel_tools import prepare_chat_ask

        cv_token = current_tenant.set(tenant) if tenant else None
        try:
            prepared = prepare_chat_ask(
                body.prompt,
                prefer=body.prefer,
                workspace_root=body.workspace_root,
                client_id=body.client_id,
                style=body.style,
                history=body.history,
            )
            if "error" in prepared:
                err = dict(prepared["error"])
                err["type"] = "error"
                yield _sse(err)
                return
            yield _sse(
                {
                    "type": "meta",
                    "used_files": prepared["used_files"],
                    "chain": [prepared["primary"], *prepared["fallbacks"]],
                }
            )
            started = time.perf_counter()
            try:
                async for ev in stream_with_cascade(
                    prepared["asked"],
                    primary=prepared["primary"],
                    fallbacks=prepared["fallbacks"],
                    max_tokens=body.max_tokens,
                    temperature=body.temperature,
                    use_cache=body.use_cache,
                    tenant_id=prepared["tenant"],
                    user_subject=prepared["user"],
                ):
                    if await request.is_disconnected():
                        # The developer pressed Stop. Nothing more is read
                        # from the provider; the generator is closed on exit.
                        logger.info("editor chat stream stopped by the client")
                        return
                    kind = ev.get("type")
                    if kind == "delta":
                        yield _sse({"type": "delta", "text": ev["text"]})
                    elif kind == "provider":
                        yield _sse(
                            {
                                "type": "provider",
                                "name": ev.get("name", ""),
                                "streams": bool(ev.get("streams", False)),
                                "cached": bool(ev.get("cached", False)),
                            }
                        )
                    elif kind == "error":
                        yield _sse(
                            {
                                "type": "error",
                                "error": "provider_failed_mid_answer",
                                "detail": ev.get("detail", ""),
                                "partial": ev.get("partial", ""),
                                "providers_tried": ev.get("providers_tried", []),
                            }
                        )
                    elif kind == "done":
                        resp = ev["response"]
                        tokens_in = int(getattr(resp, "tokens_in", 0) or 0)
                        tokens_out = int(getattr(resp, "tokens_out", 0) or 0)
                        cost: Dict[str, Any] = {}
                        try:
                            from app.chat.cost import estimate_call_cost_usd

                            cost = estimate_call_cost_usd(
                                provider=getattr(resp, "provider", None) or None,
                                tokens_in=tokens_in,
                                tokens_out=tokens_out,
                                model=getattr(resp, "model", None),
                            )
                        except Exception:  # noqa: BLE001 — an annotation
                            cost = {}
                        yield _sse(
                            {
                                "type": "done",
                                "provider": getattr(resp, "provider", "") or "",
                                "model": getattr(resp, "model", "") or "",
                                "providers_tried": list(
                                    getattr(resp, "providers_tried", []) or []
                                ),
                                "cached": bool(getattr(resp, "cached", False)),
                                "tokens_in": tokens_in,
                                "tokens_out": tokens_out,
                                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                                "cost_usd": cost.get("usd"),
                                "cost_free": cost.get("free"),
                                "truncated": bool(getattr(resp, "truncated", False)),
                                "used_files": prepared["used_files"],
                            }
                        )
            except Exception as exc:  # noqa: BLE001 — report, never 500 mid-stream
                yield _sse(
                    {
                        "type": "error",
                        "error": "cascade_failed",
                        "detail": str(exc)[:400],
                        "tried": list(prepared["active"]),
                    }
                )
        finally:
            if cv_token is not None:
                current_tenant.reset(cv_token)

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
