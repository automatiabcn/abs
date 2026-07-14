# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""`/v1/chat/*` chat UI backend.

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
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional

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
from app.licensing import gate as licence_gate
from app.cascade.orchestrator import call_with_cascade
from app.chat import (
    ChatCitation,
    build_citation_prompt_block,
    detect_pipeline,
    estimate_call_cost_usd,
    retrieve_citations,
)
from app.chat.citations import serialise_citations
from app.config import settings
from app.db.models import ChatMessage, ChatSession, User
from app.db.session import get_engine
from app.providers.cascade import get_active_providers
from app.providers.schemas import CascadeUnavailable, ProviderError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/chat", tags=["chat"])


# ───── Pydantic schemas ──────────────────────────────────────────────────

ChatRole = Literal["user", "assistant", "system", "tool"]


class ChatMessageIn(BaseModel):
    # 001/002: cascade prompt allows 1..8000 chars. Mirror those
    # bounds at the chat input so empty / oversized payloads surface as
    # 422 validation errors instead of 500ing on the cascade layer.
    role: ChatRole
    content: str = Field(..., min_length=1, max_length=8000)


class ChatCompletionsRequest(BaseModel):
    # Pre-fix `messages` was unbounded. Attacker could POST
    # 10k messages × 8000 chars (= 80 MB) and OOM the JSON+Pydantic parse
    # before any handler logic ran. Cap mirrors the OpenAI/Anthropic
    # message-window practical max (claude.ai persists ≈100 turns + system
    # before compaction); 200 leaves room for tool-augmented chains.
    #
    # NOTE: no `min_length` — the empty-list rejection is owned by the
    # handler (`if not body.messages: raise 400 messages_required`) so
    # The "400 messages_required" contract stays intact rather
    # than becoming a 422 Pydantic error.
    session_id: Optional[int] = None
    messages: List[ChatMessageIn] = Field(..., max_length=200)
    stream: bool = True
    # Explicit pipeline override; "auto" → detect
    # from the last user message; "auto_direct" skips routing entirely.
    pipeline: Literal[
        "auto",
        "auto_direct",
        "qual_code",
        "qual_tr",
        "qual_translate",
        "qual_analysis",
        "race_code",
    ] = "auto"
    # Citations are on by default; opt-out per call
    # for cheap factual chat where RAG would just add latency.
    rag_citations: bool = True
    rag_top_k: int = Field(default=5, ge=1, le=20)
    # Agent mode — let the assistant look things up (system health, spend,
    # company documents) before it answers, instead of answering from the prompt
    # alone. Opt-in per request, so plain chat stays the cheap one-shot path.
    mode: Literal["chat", "agent"] = "chat"


# Plain chat sent the user's text to the provider with nothing else attached —
# no system prompt at all. So the model answered as whatever generic assistant
# the provider had trained, and a customer who asked their own ABS server "check
# this server's status" was told, in the panel that is running on that server,
# "I'm not capable of accessing a server — try UptimeRobot or DownDetector."
#
# The preamble is deliberately short: who it is, where it runs, and what to say
# instead of claiming an incapacity the product does not have. It does not
# describe the tools — those belong to agent mode, which builds its own prompt.
ASSISTANT_PREAMBLE = (
    "You are ABS, an AI assistant running on the user's own server. "
    "The user is signed in to that server's panel; their data and documents stay "
    "on it. You answer plainly and briefly, and you do not pretend to have run "
    "anything you have not.\n"
    "You can look things up on this server — its health, its spending, its "
    "documents — but only when the user turns on Agent mode in the composer. So "
    "if a question needs live data from the server and Agent mode is off, say "
    "that it can be answered with Agent mode switched on, rather than telling the "
    "user you have no access to the machine you are running on."
)


class ChatSessionOut(BaseModel):
    id: int
    title: str
    tenant_slug: str
    user_email: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    # Threading metadata (pin / archive / sort key)
    pinned: bool = False
    archived_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    provider: Optional[str]
    tool_calls: Any = []
    # Citations are not a tool call, and returning them as one is why they used
    # to disappear. They were being written into the tool_calls blob and never
    # read back out, so an answer that streamed with its sources attached lost
    # them the moment the page rehydrated from the database — leaving the
    # model's "[4]" markers pointing at a list that was no longer on screen.
    citations: List[Dict] = []
    tokens_used: Optional[int]
    latency_ms: Optional[int]
    created_at: datetime


def _decode_tool_calls(raw: Optional[str]) -> Any:
    """The stored blob, whatever shape history left it in.

    Two shapes exist in the wild: a list of tool calls (agent mode), and a dict
    carrying the cascade's pipeline metadata with the citations inside it. Both
    have been written to this one column, so both have to be read from it.
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _stored_tool_calls(raw: Optional[str]) -> List[Any]:
    decoded = _decode_tool_calls(raw)
    if decoded is None:
        return []
    return decoded if isinstance(decoded, list) else [decoded]


def _stored_citations(raw: Optional[str]) -> List[Dict]:
    """Pull the sources back out, so a reloaded answer still shows where it came from."""
    decoded = _decode_tool_calls(raw)
    if not isinstance(decoded, dict):
        return []
    cited = decoded.get("citations")
    return [c for c in cited if isinstance(c, dict)] if isinstance(cited, list) else []


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
                "args": {"query": content[len(prefix) :].strip()},
            }
    return None


async def _run_cascade(
    prompt: str,
    max_tokens: int = 1024,
    skip_paid_providers: bool = False,
    *,
    tenant_id: str = "_global",
    project_slug: Optional[str] = None,
    user_subject: Optional[str] = None,
) -> CascadeResponse:
    """Call the cascade through the live orchestrator (`call_with_cascade`),
    bypassing the FastAPI route's auth dependency.

    This helper once raised `live_cascade_pending` even when providers were
    configured, and the chat stream turned that into a stub apology — so chat
    looked broken on a server that was perfectly capable of answering. The
    lesson it left: chat does not go through the route layer, so anything wired
    up at the route has to be wired up here too.
    """
    fallback_chain: List[str] = []
    # `cascade_req` only feeds the mock helper below; the real cascade call
    # (further down) passes the raw augmented prompt straight to the
    # orchestrator. The chat path augments the user message (≤8000 chars) with a
    # RAG grounding preamble + retrieved context, so the combined prompt can
    # legitimately exceed CascadeRequest's user-facing 8000-char DoS cap — a
    # 8000-char message + RAG injection would otherwise 500 on this validation
    # (the user limit is enforced on ChatMessageIn.content, not the augmented
    # system prompt). Clamp only the validation/mock copy; the orchestrator call
    # below still receives the full augmented prompt.
    cascade_req = CascadeRequest(prompt=prompt[:8000], max_tokens=max_tokens)

    mock_result = await _try_mock(cascade_req, fallback_chain)
    if mock_result is not None:
        return mock_result

    # MT Phase 1 — let per-owner (user/project) keys activate a provider even
    # if the operator didn't configure it globally (BYOK).
    extra: frozenset[str] = frozenset()
    if tenant_id and tenant_id != "_global":
        try:
            from app.multitenant.provider_keys import tenant_configured_providers

            extra = frozenset(
                tenant_configured_providers(
                    tenant_slug=tenant_id,
                    project_slug=project_slug,
                    user_subject=user_subject,
                )
            )
        except Exception:  # noqa: BLE001 — BYOK discovery is best-effort
            extra = frozenset()
    active = get_active_providers(skip_paid=skip_paid_providers, extra_configured=extra)
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
            tenant_id=tenant_id,
            project_slug=project_slug,
            user_subject=user_subject,
        )
    except CascadeUnavailable:
        # Everyone was busy, not broken. That is a 503 with a Retry-After — the
        # app's handler builds it. Folding it into the 502 below would tell a
        # client that something is permanently wrong and strip the one piece of
        # advice worth giving: try again in a minute.
        raise
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
    # a whitespace-only message ("   ") .strip() to "",
    # whose .splitlines() returns [] — indexing [0] raised IndexError
    # and the request 500'd before the cascade ran. Coerce to the
    # default title in that case.
    title = "New chat"
    if first_user_msg:
        first_line = next(iter(first_user_msg.strip().splitlines()), "")
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


def _load_session(db: Session, session_id: int, tenant_slug: str) -> ChatSession:
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
        message_count=message_count or sess.message_count,
        pinned=sess.pinned,
        archived_at=sess.archived_at,
        last_activity_at=sess.last_activity_at,
    )


# ───── Endpoints ─────────────────────────────────────────────────────────


@router.get("/sessions", response_model=List[ChatSessionOut])
def list_sessions(
    admin: dict = Depends(current_admin),
    search: Optional[str] = None,
    include_archived: bool = False,
):
    """Thread sidebar list.

    `search` filters case-insensitively against `title`; `include_archived`
    is False by default so archived threads stay out of the active rail.
    Ordering: pinned first, then `last_activity_at` desc.
    """
    tenant = _resolve_tenant(admin["sub"])
    with Session(get_engine()) as db:
        stmt = (
            select(ChatSession)
            .where(ChatSession.tenant_slug == tenant)
            .order_by(
                ChatSession.pinned.desc(),
                ChatSession.last_activity_at.desc(),
            )
            .limit(100)
        )
        if not include_archived:
            stmt = stmt.where(ChatSession.archived_at.is_(None))
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(ChatSession.title.ilike(like))
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
def create_session(body: NewSessionRequest, admin: dict = Depends(current_admin)):
    tenant = _resolve_tenant(admin["sub"])
    with Session(get_engine()) as db:
        sess = ChatSession(
            tenant_slug=tenant,
            user_email=admin["sub"],
            title=body.title or "New chat",
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
def delete_session(session_id: int, admin: dict = Depends(current_admin)):
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


# ───── pin / archive thread mutations ────────────────────────────────────


@router.post("/sessions/{session_id}/pin", response_model=ChatSessionOut)
def pin_session(
    session_id: int,
    pinned: bool = True,
    admin: dict = Depends(current_admin),
):
    """Toggle pin state. ``?pinned=false`` clears the pin."""
    tenant = _resolve_tenant(admin["sub"])
    with Session(get_engine()) as db:
        sess = _load_session(db, session_id, tenant)
        sess.pinned = bool(pinned)
        sess.updated_at = datetime.now(timezone.utc)
        db.add(sess)
        db.commit()
        db.refresh(sess)
        return _session_out(sess, sess.message_count)


@router.post("/sessions/{session_id}/archive", response_model=ChatSessionOut)
def archive_session(
    session_id: int,
    admin: dict = Depends(current_admin),
):
    """Set ``archived_at`` (idempotent — re-archive keeps original ts)."""
    tenant = _resolve_tenant(admin["sub"])
    with Session(get_engine()) as db:
        sess = _load_session(db, session_id, tenant)
        if sess.archived_at is None:
            sess.archived_at = datetime.now(timezone.utc)
            sess.updated_at = sess.archived_at
            db.add(sess)
            db.commit()
            db.refresh(sess)
        return _session_out(sess, sess.message_count)


@router.post("/sessions/{session_id}/unarchive", response_model=ChatSessionOut)
def unarchive_session(
    session_id: int,
    admin: dict = Depends(current_admin),
):
    tenant = _resolve_tenant(admin["sub"])
    with Session(get_engine()) as db:
        sess = _load_session(db, session_id, tenant)
        if sess.archived_at is not None:
            sess.archived_at = None
            sess.updated_at = datetime.now(timezone.utc)
            db.add(sess)
            db.commit()
            db.refresh(sess)
        return _session_out(sess, sess.message_count)


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageOut])
def list_messages(session_id: int, admin: dict = Depends(current_admin)):
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
                tool_calls=_stored_tool_calls(m.tool_calls),
                citations=_stored_citations(m.tool_calls),
                tokens_used=m.tokens_used,
                latency_ms=m.latency_ms,
                created_at=m.created_at,
            )
            for m in msgs
        ]


def _assert_license_ok() -> None:
    """Refuse the request when — and only when — the licence itself is bad.

    This used to read a cached activation state and, whenever that cache was
    missing or older than 30 seconds, block the request on a *synchronous
    heartbeat* to our activation server. Which meant:

      * a fresh install answered 403 `license_not_activated` to its very first
        chat message, because it had not phoned home yet;
      * our activation host sat in the request path of every chat turn on every
        customer's machine, behind a 3-second timeout;
      * "we could not reach the licence server" and "this licence is revoked"
        produced the same refusal, so any outage of ours — or any customer
        firewall — killed the product they had paid for.

    `app.licensing.gate` decides all of this offline, from the signature on the
    key. Revocation still bites, because the persisted state can only have been
    written by a real server response; a missing cache means we have not
    managed to ask, and that is not the customer's fault. See the module
    docstring there for the full rule.
    """
    decision = licence_gate.enforce()
    if decision.allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=decision.detail,
    )


@router.post("/completions")
async def completions(
    body: ChatCompletionsRequest,
    request: Request,
    admin: dict = Depends(current_admin),
):
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages_required")
    if body.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="last_message_must_be_user")
    _assert_license_ok()

    admin_email = admin["sub"]
    tenant = _resolve_tenant(admin_email)
    last_user_content = body.messages[-1].content

    # Multi-turn chat history. Pre-fix the handler persisted
    # only the last user message and shipped only that string to the
    # cascade orchestrator, so the assistant lost prior context as soon
    # as the client included earlier turns in body.messages. Now any
    # messages in body.messages not already in DB get persisted, and
    # the cascade prompt is rendered from the full history below.

    with Session(get_engine()) as db:
        if body.session_id:
            sess = _load_session(db, body.session_id, tenant)
        else:
            sess = _create_session(db, tenant, admin_email, last_user_content)
        sess_id = sess.id
        sess_title = sess.title

        existing_count = int(
            db.exec(
                select(func.count(ChatMessage.id)).where(
                    ChatMessage.session_id == sess_id
                )
            ).one()
            or 0
        )
        new_msgs = (
            body.messages[existing_count:] if existing_count else list(body.messages)
        )
        for m in new_msgs:
            db.add(
                ChatMessage(
                    session_id=sess_id,
                    role=m.role,
                    content=m.content,
                )
            )
        # Bump the sidebar denorm columns. The
        # assistant-message branch later adds another +1 on its own
        # commit, so user + assistant each contribute one.
        sess.last_activity_at = datetime.now(timezone.utc)
        sess.message_count = (sess.message_count or 0) + len(new_msgs)
        db.add(sess)
        db.commit()

    cmd = _detect_slash_command(last_user_content)

    # Pipeline routing decision (auto / explicit).
    if body.pipeline == "auto":
        pipeline_used = detect_pipeline(last_user_content)
    else:
        pipeline_used = body.pipeline

    # Pre-flight provider probe. With every provider disabled, opening the SSE
    # Stream first would send HTTP 200 and then yield an error inside the body,
    # so a fetch() client sees response.ok = true and loses its retry
    # Semantics. Answering with a structured 503 BEFORE the stream starts keeps
    # ok=false and the Retry-After contract intact.
    #
    # Skip when:
    #   - a qual_* pipeline is selected (it orchestrates providers itself)
    #   - the Anthropic mock provider is active (test/dev path; _try_mock
    #     Still runs inside the stream)
    if body.pipeline in ("auto", "cascade") and pipeline_used not in (
        "qual_code",
        "qual_tr",
        "qual_analysis",
        "qual_translate",
    ):
        try:
            from app.providers.anthropic_mock import get_mock_provider

            _mock_active = get_mock_provider() is not None
        except Exception:
            _mock_active = False
        if not _mock_active:
            try:
                _probe_active = get_active_providers(skip_paid=False)
            except Exception:
                _probe_active = []
            if not _probe_active:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "all_providers_unavailable",
                        "providers_tried": [],
                        "retry_after": 60,
                        "hint": "Add at least one provider key under Settings → Providers.",
                    },
                    headers={"Retry-After": "60"},
                )

    async def agent_stream() -> AsyncGenerator[str, None]:
        """Agent mode — the assistant may look things up before it answers.

        A separate stream from plain chat on purpose: the loop owns its own
        provider calls (one per step, whole transcript re-sent) and its own
        events, and folding that into the single-shot path would leave both
        harder to follow. What the two share is what the client depends on —
        the opening `session` frame, the assistant message landing in the
        session, and `[DONE]`.
        """
        from app.agentic.loop import run_agent_loop

        yield f"data: {json.dumps({'type': 'session', 'session_id': sess_id, 'title': sess_title})}\n\n"
        yield f"data: {json.dumps({'type': 'mode', 'id': 'agent'})}\n\n"

        t_agent = time.perf_counter()
        try:
            providers = get_active_providers(skip_paid=False)
        except Exception:
            providers = []
        if not providers:
            err = (
                "No provider is set up yet, so there is nothing to answer with. "
                "Add a key under Settings → Providers."
            )
            yield f"data: {json.dumps({'type': 'text', 'content': err, 'provider': 'none'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        answer = ""
        tool_calls: List[Dict] = []
        async for event in run_agent_loop(
            user_message=last_user_content,
            providers=providers,
            tenant=tenant,
            requester=admin_email,
        ):
            yield event.sse()
            if event.type == "tool-call":
                tool_calls.append(
                    {"name": event.data.get("name"), "args": event.data.get("args")}
                )
            elif event.type == "agent-done":
                answer = str(event.data.get("answer") or "")
            elif event.type == "agent-error":
                answer = (
                    "No provider answered. Try again in a moment."
                    if event.data.get("reason") == "all_providers_failed"
                    else "Agent mode is not available right now."
                )

        # The answer is streamed in one frame rather than chunked: the loop has
        # already given the client something to render at every step, so the
        # typewriter effect buys nothing and delays the payload.
        if answer:
            yield f"data: {json.dumps({'type': 'text', 'content': answer, 'provider': 'agent'})}\n\n"

        with Session(get_engine()) as db:
            db.add(
                ChatMessage(
                    session_id=sess_id,
                    role="assistant",
                    content=answer,
                    provider="agent",
                    latency_ms=int((time.perf_counter() - t_agent) * 1000),
                    # The transcript keeps the receipt: which tools ran, with
                    # what arguments. An operator auditing a surprising answer
                    # can see what the assistant looked at to produce it.
                    tool_calls=(
                        json.dumps(tool_calls, ensure_ascii=False)[:8192]
                        if tool_calls
                        else None
                    ),
                )
            )
            touched = db.get(ChatSession, sess_id)
            if touched is not None:
                now = datetime.now(timezone.utc)
                touched.updated_at = now
                touched.last_activity_at = now
                touched.message_count = (touched.message_count or 0) + 1
                db.add(touched)
            db.commit()

        yield "data: [DONE]\n\n"

    async def stream() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type': 'session', 'session_id': sess_id, 'title': sess_title})}\n\n"
        yield f"data: {json.dumps({'type': 'pipeline', 'id': pipeline_used})}\n\n"

        if cmd:
            yield f"data: {json.dumps({'type': 'tool-call', 'name': cmd['name'], 'args': cmd['args']})}\n\n"
            if cmd["name"] == "rag":
                stub = {
                    "type": "tool-result",
                    "name": "rag_query",
                    "result": (
                        f"[RAG stub] Live results for '{cmd['args']['query']}' "
                        "are not wired up yet."
                    ),
                }
                yield f"data: {json.dumps(stub)}\n\n"

        # RAG-grounded citations: pull top-K chunks
        # before the cascade call, inject as a [1]/[2]/… block, and ship
        # the structured citation list in the closing `meta` event. Pure
        # no-op when retrieval fails or returns nothing — no hallucinated
        # citations are ever emitted.
        citations: List[ChatCitation] = []
        if body.rag_citations:
            try:
                citations = await retrieve_citations(
                    last_user_content,
                    project=tenant,
                    top_k=body.rag_top_k,
                )
            except Exception as exc:  # pragma: no cover — defensive only
                logger.info("citation retrieval skipped: %s", exc)
                citations = []
            if citations:
                yield f"data: {json.dumps({'type': 'citations', 'citations': serialise_citations(citations)})}\n\n"

        # Multi-turn rendering. Build a "User: …\nAssistant: …"
        # transcript from body.messages and append the citation-augmented
        # last user line. Single-turn requests (one user msg) collapse
        # to the previous behaviour: just the user content + citations.
        if len(body.messages) > 1:
            history_lines: list[str] = []
            for m in body.messages[:-1]:
                role_label = (
                    "User"
                    if m.role == "user"
                    else ("Assistant" if m.role == "assistant" else m.role.capitalize())
                )
                history_lines.append(f"{role_label}: {m.content}")
            transcript = "\n".join(history_lines)
            last_with_citations = build_citation_prompt_block(
                citations, user_message=last_user_content
            )
            prompt_for_cascade = f"{transcript}\nUser: {last_with_citations}"
        else:
            prompt_for_cascade = build_citation_prompt_block(
                citations, user_message=last_user_content
            )

        prompt_for_cascade = f"{ASSISTANT_PREAMBLE}\n\n{prompt_for_cascade}"

        # Emit a "thinking" frame before the cascade call
        # so the client (and any intermediate proxy / load balancer) sees
        # SSE traffic well within the 30s idle-timeout window. Live
        # provider calls can run 5-30s; without this beat a slow
        # provider would silently disconnect mid-request.
        yield f"data: {json.dumps({'type': 'thinking'})}\n\n"

        t0 = time.perf_counter()
        # Qual_* dedicated multi-model pipelines.
        from app.pipelines.qual import QUAL_HANDLERS as _QUAL_HANDLERS
        from app.pipelines.qual import run_qual_pipeline as _run_qual

        qual_meta: Optional[Dict] = None
        try:
            if pipeline_used in _QUAL_HANDLERS:
                qual_result = await _run_qual(pipeline_used, prompt_for_cascade)
                qual_meta = qual_result.to_dict()
                cascade_resp = CascadeResponse(
                    completion=qual_result.completion or "",
                    provider=(
                        qual_result.providers[-1] if qual_result.providers else "qual"
                    ),
                    fallback_chain=list(qual_result.providers) or ["qual"],
                    tokens_used=0,
                    mock=False,
                    cached=False,
                    elapsed_ms=qual_result.elapsed_ms,
                    model=pipeline_used,
                )
            else:
                cascade_resp = await _run_cascade(
                    prompt_for_cascade,
                    tenant_id=tenant,
                    project_slug=(request.headers.get("X-Project-Id") or None),
                    user_subject=admin_email,
                )
        except HTTPException as exc:
            detail_str = str(exc.detail or "")
            if detail_str.startswith("no_providers_configured"):
                err_text = (
                    "No provider is set up yet, so there is nothing to answer "
                    "with. Add a key under Settings → Providers."
                )
            elif detail_str.startswith("no_free_providers_configured"):
                err_text = (
                    "Only paid providers are configured, and this server is set "
                    "to use free ones. Add a free provider, or allow paid ones."
                )
            elif detail_str.startswith("all_providers_failed"):
                err_text = (
                    "Every provider failed on this question. Try again in a moment."
                )
            else:
                err_text = "The answer did not come through. Try again."
            yield f"data: {json.dumps({'type': 'text', 'content': err_text, 'provider': 'none'})}\n\n"
            yield "data: [DONE]\n\n"
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
                    now = datetime.now(timezone.utc)
                    touched.updated_at = now
                    # Keep the sidebar-sort denorm
                    # columns in step with the actual chat traffic.
                    touched.last_activity_at = now
                    touched.message_count = (touched.message_count or 0) + 1
                    db.add(touched)
                db.commit()
            return

        text = cascade_resp.completion
        provider = cascade_resp.provider
        chunk_size = 32
        for i in range(0, len(text), chunk_size):
            payload = {
                "type": "text",
                "content": text[i : i + chunk_size],
                "provider": provider,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.01)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        # Provider transparency: emit cost USD +
        # cascade chain so the message footer can show the receipt.
        # `tokens_in` / `tokens_out` are best-effort: the cascade
        # response only exposes the combined `tokens_used`, so we split
        # 30/70 input/output the same way `cost_estimator.py` does.
        tin = int(round((cascade_resp.tokens_used or 0) * 0.3))
        tout = max(0, (cascade_resp.tokens_used or 0) - tin)
        cost_info = estimate_call_cost_usd(
            provider=provider,
            tokens_in=tin,
            tokens_out=tout,
            model=getattr(cascade_resp, "model", None),
        )
        meta = {
            "type": "meta",
            "provider": provider,
            "fallback_chain": cascade_resp.fallback_chain,
            "tokens_used": cascade_resp.tokens_used,
            "latency_ms": latency_ms,
            "mock": cascade_resp.mock,
            "pipeline": pipeline_used,
            "cost_usd": cost_info["usd"],
            "free": cost_info["free"],
            "citation_count": len(citations),
        }
        if qual_meta is not None:
            meta["qual"] = {
                "verified": qual_meta.get("verified", False),
                "revisions": qual_meta.get("revisions", 0),
                "stages": qual_meta.get("stages", []),
                "fallback": qual_meta.get("fallback", False),
                "fallback_reason": qual_meta.get("fallback_reason"),
            }
        if qual_meta is not None:
            meta["qual"] = {
                "verified": qual_meta.get("verified", False),
                "revisions": qual_meta.get("revisions", 0),
                "stages": qual_meta.get("stages", []),
                "fallback": qual_meta.get("fallback", False),
                "fallback_reason": qual_meta.get("fallback_reason"),
            }
        yield f"data: {json.dumps(meta)}\n\n"
        yield "data: [DONE]\n\n"

        with Session(get_engine()) as db:
            tool_calls_json = (
                json.dumps(
                    {
                        "pipeline": pipeline_used,
                        "citations": serialise_citations(citations),
                        "fallback_chain": cascade_resp.fallback_chain,
                        "cost_usd": cost_info["usd"],
                        "free": cost_info["free"],
                    },
                    ensure_ascii=False,
                )
                if (citations or pipeline_used != "auto_direct")
                else None
            )
            db.add(
                ChatMessage(
                    session_id=sess_id,
                    role="assistant",
                    content=text,
                    provider=provider,
                    tokens_used=cascade_resp.tokens_used,
                    latency_ms=latency_ms,
                    tool_calls=tool_calls_json,
                )
            )
            touched = db.get(ChatSession, sess_id)
            if touched is not None:
                touched.updated_at = datetime.now(timezone.utc)
                db.add(touched)
            db.commit()

    # Agent mode is a request-level choice, and only honoured if the operator
    # left it enabled on this server: `mode="agent"` from a client cannot switch
    # on a capability the settings turned off.
    use_agent = body.mode == "agent" and settings.agent_mode_enabled

    return StreamingResponse(
        agent_stream() if use_agent else stream(),
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
