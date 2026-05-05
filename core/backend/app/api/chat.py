"""Q8 / Phase A — `/v1/chat/*` chat UI backend.

Streams SSE responses from the cascade router (mock or real providers),
persists session + messages, and exposes session CRUD for the panel
sidebar. Slash commands (`/rag`, `/code`, `/translate`, `/analyze`,
`/workflow`) emit tool-call events before the cascade run.

Auth: panel session cookie via `current_admin`. Tenant resolved from the
`users` table; falls back to `"default"` for the bootstrap admin.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.auth import current_admin
from app.api.cascade import (
    CascadeRequest,
    CascadeResponse,
    _try_mock,
)
from app.cascade.orchestrator import call_with_cascade
from app.db.models import ChatMessage, ChatSession, User
from app.db.session import get_engine
from app.providers.cascade import get_active_providers
from app.providers.schemas import ProviderError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/chat", tags=["chat"])


# ───── Pydantic schemas ──────────────────────────────────────────────────

ChatRole = Literal["user", "assistant", "system", "tool"]


class ChatMessageIn(BaseModel):
    # Q11-L13-001/002: cascade prompt allows 1..8000 chars. Mirror those
    # bounds at the chat input so empty / oversized payloads surface as
    # 422 validation errors instead of 500ing on the cascade layer.
    role: ChatRole
    content: str = Field(..., min_length=1, max_length=8000)


class ChatCompletionsRequest(BaseModel):
    # Q12-L25-003 — pre-fix `messages` was unbounded. Attacker could POST
    # 10k messages × 8000 chars (= 80 MB) and OOM the JSON+Pydantic parse
    # before any handler logic ran. Cap mirrors the OpenAI/Anthropic
    # message-window practical max (claude.ai persists ≈100 turns + system
    # before compaction); 200 leaves room for tool-augmented chains.
    #
    # NOTE: no `min_length` — the empty-list rejection is owned by the
    # handler (`if not body.messages: raise 400 messages_required`) so
    # the Q10-L1 contract ("400 messages_required") stays intact rather
    # than becoming a 422 Pydantic error.
    session_id: Optional[int] = None
    messages: List[ChatMessageIn] = Field(..., max_length=200)
    stream: bool = True


class ChatSessionOut(BaseModel):
    id: int
    title: str
    tenant_slug: str
    user_email: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    provider: Optional[str]
    tool_calls: Optional[Dict]
    tokens_used: Optional[int]
    latency_ms: Optional[int]
    created_at: datetime


class NewSessionRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


# ───── Helpers ───────────────────────────────────────────────────────────


def _resolve_tenant(admin_email: str) -> str:
    """Look up tenant_slug from the users table; default if absent."""
    try:
        with Session(get_engine()) as db:
            stmt = (
                select(User)
                .where(User.email == admin_email)
                .where(User.status == "active")
            )
            user = db.exec(stmt).first()
            return user.tenant_slug if user else "default"
    except Exception as exc:  # pragma: no cover — boot before users table
        logger.debug("tenant resolution fell back to default: %s", exc)
        return "default"


SLASH_COMMANDS = {
    "/rag ": "rag",
    "/workflow ": "workflow",
    "/code ": "code",
    "/translate ": "translate",
    "/analyze ": "analyze",
}


def _detect_slash_command(content: str) -> Optional[Dict]:
    for prefix, name in SLASH_COMMANDS.items():
        if content.startswith(prefix):
            return {
                "name": name,
                "args": {"query": content[len(prefix):].strip()},
            }
    return None


async def _run_cascade(
    prompt: str,
    max_tokens: int = 1024,
    skip_paid_providers: bool = False,
) -> CascadeResponse:
    """Bypass the FastAPI route's auth dependency and call the cascade
    via the live orchestrator (`call_with_cascade`).

    Round-4 BUG-9 fix: previously raised `live_cascade_pending` 503 even
    when providers were configured; the chat SSE swallowed that into a
    "Cascade canli uclari henuz aktif degil." stub message. The /v1/cascade/run
    route was wired in Round 2 but this helper was missed — chat path
    bypasses the route layer, so it stayed stubbed until Round 4.
    """
    fallback_chain: List[str] = []
    cascade_req = CascadeRequest(prompt=prompt, max_tokens=max_tokens)

    mock_result = await _try_mock(cascade_req, fallback_chain)
    if mock_result is not None:
        return mock_result

    active = get_active_providers(skip_paid=skip_paid_providers)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "no_free_providers_configured"
                if skip_paid_providers
                else "no_providers_configured"
            ),
        )

    primary, *rest = active
    try:
        resp = await call_with_cascade(
            prompt,
            primary=primary,
            fallbacks=tuple(rest),
            max_tokens=max_tokens,
        )
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"all_providers_failed: {exc.message or str(exc)} "
                f"(chain={','.join(active)})"
            ),
        ) from exc

    tokens_used = (resp.tokens_in or 0) + (resp.tokens_out or 0)
    return CascadeResponse(
        completion=resp.text,
        provider=resp.provider or primary,
        fallback_chain=[resp.provider or primary],
        tokens_used=tokens_used,
        mock=False,
        cached=resp.cached,
        elapsed_ms=resp.elapsed_ms,
        model=resp.model,
    )


def _create_session(
    db: Session, tenant_slug: str, user_email: str, first_user_msg: Optional[str]
) -> ChatSession:
    # Q11-L13-003: a whitespace-only message ("   ") .strip() to "",
    # whose .splitlines() returns [] — indexing [0] raised IndexError
    # and the request 500'd before the cascade ran. Coerce to the
    # default title in that case.
    title = "Yeni sohbet"
    if first_user_msg:
        first_line = next(
            iter(first_user_msg.strip().splitlines()), ""
        )
        if first_line:
            title = first_line[:60]
    sess = ChatSession(
        tenant_slug=tenant_slug,
        user_email=user_email,
        title=title,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def _load_session(
    db: Session, session_id: int, tenant_slug: str
) -> ChatSession:
    sess = db.get(ChatSession, session_id)
    if not sess or sess.tenant_slug != tenant_slug:
        raise HTTPException(status_code=404, detail="session_not_found")
    return sess


def _session_out(sess: ChatSession, message_count: int) -> ChatSessionOut:
    return ChatSessionOut(
        id=sess.id,
        title=sess.title,
        tenant_slug=sess.tenant_slug,
        user_email=sess.user_email,
        created_at=sess.created_at,
        updated_at=sess.updated_at,
        message_count=message_count,
    )


# ───── Endpoints ─────────────────────────────────────────────────────────


@router.get("/sessions", response_model=List[ChatSessionOut])
def list_sessions(admin: dict = Depends(current_admin)):
    tenant = _resolve_tenant(admin["sub"])
    with Session(get_engine()) as db:
        stmt = (
            select(ChatSession)
            .where(ChatSession.tenant_slug == tenant)
            .order_by(ChatSession.updated_at.desc())
            .limit(50)
        )
        sessions = db.exec(stmt).all()
        if not sessions:
            return []

        ids = [s.id for s in sessions]
        count_rows = db.exec(
            select(ChatMessage.session_id, func.count(ChatMessage.id))
            .where(ChatMessage.session_id.in_(ids))
            .group_by(ChatMessage.session_id)
        ).all()
        counts = {row[0]: row[1] for row in count_rows}
        return [_session_out(s, counts.get(s.id, 0)) for s in sessions]


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
def create_session(
    body: NewSessionRequest, admin: dict = Depends(current_admin)
):
    tenant = _resolve_tenant(admin["sub"])
    with Session(get_engine()) as db:
        sess = ChatSession(
            tenant_slug=tenant,
            user_email=admin["sub"],
            title=body.title or "Yeni sohbet",
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        return _session_out(sess, 0)


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
def rename_session(
    session_id: int,
    body: NewSessionRequest,
    admin: dict = Depends(current_admin),
):
    tenant = _resolve_tenant(admin["sub"])
    with Session(get_engine()) as db:
        sess = _load_session(db, session_id, tenant)
        if body.title:
            sess.title = body.title
            sess.updated_at = datetime.now(timezone.utc)
            db.add(sess)
            db.commit()
            db.refresh(sess)
        cnt_row = db.exec(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.session_id == session_id
            )
        ).one()
        message_count = cnt_row[0] if isinstance(cnt_row, tuple) else cnt_row
        return _session_out(sess, message_count or 0)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: int, admin: dict = Depends(current_admin)
):
    tenant = _resolve_tenant(admin["sub"])
    with Session(get_engine()) as db:
        sess = _load_session(db, session_id, tenant)
        # Iterate-and-delete keeps SQLite consistent without a FK cascade.
        for msg in db.exec(
            select(ChatMessage).where(ChatMessage.session_id == session_id)
        ).all():
            db.delete(msg)
        db.delete(sess)
        db.commit()
    return None


@router.get(
    "/sessions/{session_id}/messages", response_model=List[ChatMessageOut]
)
def list_messages(
    session_id: int, admin: dict = Depends(current_admin)
):
    tenant = _resolve_tenant(admin["sub"])
    with Session(get_engine()) as db:
        _load_session(db, session_id, tenant)
        msgs = db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        ).all()
        return [
            ChatMessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                provider=m.provider,
                tool_calls=json.loads(m.tool_calls) if m.tool_calls else None,
                tokens_used=m.tokens_used,
                latency_ms=m.latency_ms,
                created_at=m.created_at,
            )
            for m in msgs
        ]


@router.post("/completions")
async def completions(
    body: ChatCompletionsRequest,
    request: Request,
    admin: dict = Depends(current_admin),
):
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages_required")
    if body.messages[-1].role != "user":
        raise HTTPException(
            status_code=400, detail="last_message_must_be_user"
        )

    admin_email = admin["sub"]
    tenant = _resolve_tenant(admin_email)
    last_user_content = body.messages[-1].content

    # Persist user message + create session before streaming so the panel
    # sidebar reflects the conversation even if the client disconnects.
    with Session(get_engine()) as db:
        if body.session_id:
            sess = _load_session(db, body.session_id, tenant)
        else:
            sess = _create_session(db, tenant, admin_email, last_user_content)
        sess_id = sess.id
        sess_title = sess.title

        user_msg = ChatMessage(
            session_id=sess_id,
            role="user",
            content=last_user_content,
        )
        db.add(user_msg)
        db.commit()

    cmd = _detect_slash_command(last_user_content)

    async def stream() -> AsyncGenerator[str, None]:
        yield f'data: {json.dumps({"type": "session", "session_id": sess_id, "title": sess_title})}\n\n'

        if cmd:
            yield f'data: {json.dumps({"type": "tool-call", "name": cmd["name"], "args": cmd["args"]})}\n\n'
            if cmd["name"] == "rag":
                stub = {
                    "type": "tool-result",
                    "name": "rag_query",
                    "result": (
                        f"[RAG stub] '{cmd['args']['query']}' icin "
                        "Phase F'te canli sonuc gelecek."
                    ),
                }
                yield f'data: {json.dumps(stub)}\n\n'

        # Q11-L10-002: emit a "thinking" frame before the cascade call
        # so the client (and any intermediate proxy / load balancer) sees
        # SSE traffic well within the 30s idle-timeout window. Live
        # provider calls can run 5-30s; without this beat a slow
        # provider would silently disconnect mid-request.
        yield f'data: {json.dumps({"type": "thinking"})}\n\n'

        t0 = time.perf_counter()
        try:
            cascade_resp = await _run_cascade(last_user_content)
        except HTTPException as exc:
            detail_str = str(exc.detail or "")
            if detail_str.startswith("no_providers_configured"):
                err_text = (
                    "Henuz saglayici yapilandirilmadi. "
                    "/admin/settings → Providers."
                )
            elif detail_str.startswith("no_free_providers_configured"):
                err_text = (
                    "Ucretsiz saglayici yapilandirilmadi "
                    "(skip_paid aktif)."
                )
            elif detail_str.startswith("all_providers_failed"):
                err_text = (
                    "Tum saglayicilar gecici hata verdi; "
                    "lutfen tekrar deneyin."
                )
            else:
                err_text = "Cascade canli uclari henuz aktif degil."
            yield f'data: {json.dumps({"type": "text", "content": err_text, "provider": "none"})}\n\n'
            yield 'data: [DONE]\n\n'
            with Session(get_engine()) as db:
                db.add(
                    ChatMessage(
                        session_id=sess_id,
                        role="assistant",
                        content=err_text,
                        provider="none",
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                    )
                )
                touched = db.get(ChatSession, sess_id)
                if touched is not None:
                    touched.updated_at = datetime.now(timezone.utc)
                    db.add(touched)
                db.commit()
            return

        text = cascade_resp.completion
        provider = cascade_resp.provider
        chunk_size = 32
        for i in range(0, len(text), chunk_size):
            payload = {
                "type": "text",
                "content": text[i:i + chunk_size],
                "provider": provider,
            }
            yield f'data: {json.dumps(payload)}\n\n'
            await asyncio.sleep(0.01)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        meta = {
            "type": "meta",
            "provider": provider,
            "fallback_chain": cascade_resp.fallback_chain,
            "tokens_used": cascade_resp.tokens_used,
            "latency_ms": latency_ms,
            "mock": cascade_resp.mock,
        }
        yield f'data: {json.dumps(meta)}\n\n'
        yield 'data: [DONE]\n\n'

        with Session(get_engine()) as db:
            db.add(
                ChatMessage(
                    session_id=sess_id,
                    role="assistant",
                    content=text,
                    provider=provider,
                    tokens_used=cascade_resp.tokens_used,
                    latency_ms=latency_ms,
                )
            )
            touched = db.get(ChatSession, sess_id)
            if touched is not None:
                touched.updated_at = datetime.now(timezone.utc)
                db.add(touched)
            db.commit()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


__all__ = [
    "ChatCompletionsRequest",
    "ChatMessageIn",
    "ChatMessageOut",
    "ChatSessionOut",
    "NewSessionRequest",
    "router",
]
