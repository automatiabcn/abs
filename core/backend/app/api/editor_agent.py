# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The editor agent's two routes.

    POST /v1/editor/agent/step   — one step of the loop, streamed (see
                                   app.editor_agent.step for the events)
    POST /v1/editor/agent/tool   — run one of the tools that live on the
                                   server: semantic_search, propose_edit

Guarded exactly like the chat stream beside it: the editor's `abs_mcp_`
bearer token, the same scope rule, the same licence gate. Nothing here
writes to the developer's project — propose_edit returns a diff; the
editor applies it, after a click, on the developer's machine.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.editor_chat import _bearer, _licence_allows
from app.editor_agent.step import StepRequest, run_step

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/editor/agent", tags=["editor-agent"])


def _sse(obj: Dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/step")
async def agent_step(body: StepRequest, request: Request) -> StreamingResponse:
    payload = _bearer(request)
    refused = _licence_allows()
    if refused:

        async def _refuse() -> AsyncIterator[str]:
            yield _sse({"type": "error", "error": "subscription_required", "detail": refused})

        return StreamingResponse(_refuse(), media_type="text/event-stream")

    from app.mcp.context import set_mcp_caller

    set_mcp_caller(payload.get("tenant"), payload.get("actor"))
    tenant = str(payload.get("tenant") or "").strip() or "_global"
    user = str(payload.get("actor") or "").strip()

    async def _events() -> AsyncIterator[str]:
        from app.db.session import current_tenant

        cv_token = current_tenant.set(tenant) if tenant != "_global" else None
        try:
            async for ev in run_step(
                body, tenant=tenant, user=user, is_disconnected=request.is_disconnected
            ):
                yield _sse(ev)
        except asyncio.CancelledError:
            logger.info("editor agent step cancelled — the client left")
            raise
        except Exception as exc:  # noqa: BLE001 — report, never 500 mid-stream
            yield _sse({"type": "error", "error": "step_failed", "detail": str(exc)[:400]})
        finally:
            if cv_token is not None:
                current_tenant.reset(cv_token)

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ToolRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    args: Dict[str, Any] = Field(default_factory=dict)
    workspace_root: str = ""
    client_id: str = ""


@router.post("/tool")
async def agent_tool(body: ToolRequest, request: Request) -> Dict[str, Any]:
    payload = _bearer(request)
    refused = _licence_allows()
    if refused:
        return {"ok": False, "error": "subscription_required", "model_note": refused}

    from app.mcp.context import set_mcp_caller
    from app.workspace.current import current_workspace

    set_mcp_caller(payload.get("tenant"), payload.get("actor"))
    tenant = str(payload.get("tenant") or "").strip() or "_global"
    user = str(payload.get("actor") or "").strip()
    root = current_workspace(
        tenant, user, client_id=body.client_id, explicit_root=body.workspace_root
    )
    if not root:
        return {
            "ok": False,
            "error": "no_workspace",
            "model_note": "System: no project folder is open on this editor, so the tool cannot run.",
        }
    if body.name == "semantic_search":
        from app.editor_agent.search import semantic_search

        return await semantic_search(
            root=root, query=str(body.args.get("query") or ""), tenant=tenant
        )
    if body.name == "propose_edit":
        from app.editor_agent.edits import propose_edit

        a = body.args
        return await propose_edit(
            root=root,
            path=str(a.get("path") or ""),
            search=str(a.get("search") or ""),
            replace=str(a.get("replace") or ""),
            new_content=a.get("new_content") if isinstance(a.get("new_content"), str) else None,
            rationale=str(a.get("rationale") or ""),
            tenant=tenant if tenant != "_global" else None,
            user=user or None,
        )
    return {
        "ok": False,
        "error": "not_a_server_tool",
        "model_note": f"System: '{body.name}' is not a tool this server runs.",
    }
