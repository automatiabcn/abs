# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

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
from app.licensing.phone_home import (
    cache_age_seconds,
    force_heartbeat_sync,
    get_cached_license_state,
)
from app.cascade.orchestrator import call_with_cascade
from app.chat import (
    PIPELINE_OPTIONS,
    ChatCitation,
    build_citation_prompt_block,
    detect_pipeline,
    estimate_call_cost_usd,
    retrieve_citations,
)
from app.chat.citations import serialise_citations
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
    # Q12 / Brief 3 R2 — explicit pipeline override; "auto" → detect
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
    # Q12 / Brief 3 R1 — citations are on by default; opt-out per call
    # for cheap factual chat where RAG would just add latency.
    rag_citations: bool = True
    rag_top_k: int = Field(default=5, ge=1, le=20)


class ChatSessionOut(BaseModel):
    id: int
    title: str
    tenant_slug: str
    user_email: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    # Q12 / Brief 3 R4 — threading metadata (pin / archive / sort key)
    pinned: bool = False
    archived_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    provider: Optional[str]
    tool_calls: Any = []
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
    "Cascade canlı uçları henüz aktif değil." stub message. The /v1/cascade/run
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
    """Q12 / Brief 3 R4 — thread sidebar list.

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


# ───── Q12 / Brief 3 R4 — pin / archive thread mutations ─────────────────


@router.post(
    "/sessions/{session_id}/pin", response_model=ChatSessionOut
)
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


@router.post(
    "/sessions/{session_id}/archive", response_model=ChatSessionOut
)
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


@router.post(
    "/sessions/{session_id}/unarchive", response_model=ChatSessionOut
)
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
                tool_calls=(
                    (
                        json.loads(m.tool_calls)
                        if isinstance(json.loads(m.tool_calls), list)
                        else [json.loads(m.tool_calls)]
                    )
                    if m.tool_calls
                    else []
                ),
                tokens_used=m.tokens_used,
                latency_ms=m.latency_ms,
                created_at=m.created_at,
            )
            for m in msgs
        ]


_LICENSE_GATE_STALE_SECS = 30.0


def _assert_license_ok() -> None:
    """BUG-21 — pre-flight license cache gate with sync heartbeat refresh.

    The cascade router already gates paid providers via quota_monitor, but
    the chat endpoint itself used to happily stream mock responses to a
    revoked tenant for up to one heartbeat interval (60s).  The new flow:

    1. Read the cached activation state.
    2. If the cache is missing, **or** older than
       ``_LICENSE_GATE_STALE_SECS``, trigger a synchronous heartbeat
       (best-effort, 3s timeout, 5s cooldown across requests). A
       server-side revoke now propagates to the chat path within seconds
       instead of waiting on the next 60s tick.
    3. Refuse the request unless the (possibly refreshed) state has
       ``valid=true``. Missing state after a refresh attempt means we
       could not contact the activation server *and* never had a prior
       successful activation — fail-closed so a fresh, never-activated
       container cannot bypass the gate.

    Honours ``ABS_TEST_MODE=1`` and ``ABS_LICENSE_GATE_DISABLED=1`` so
    the unit suite + dev environments are unaffected.
    """
    import os

    if os.environ.get("ABS_TEST_MODE") == "1":
        return
    if os.environ.get("ABS_LICENSE_GATE_DISABLED") == "1":
        return

    # Demo mode (ABS_DEMO_MODE) — allow chat so a showcase install can exercise
    # the playground, consistent with the MCP gate (app/mcp/gate.py already
    # treats demo_active as allowed). Without this the demo could delegate via
    # /mcp but the panel chat returned 403 license_not_activated — an
    # inconsistent, confusing demo experience. Real customers run with a
    # license (demo off), so the license path below still applies to them.
    try:
        from app.licensing.demo import is_active as _demo_active

        if _demo_active():
            return
    except Exception:
        pass

    state = get_cached_license_state()
    age = cache_age_seconds()
    if not state or age is None or age > _LICENSE_GATE_STALE_SECS:
        refreshed = force_heartbeat_sync()
        if refreshed is not None:
            state = refreshed

    if not state:
        # No prior activation, no successful sync refresh → fail-closed.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="license_not_activated",
        )

    if not state.get("valid", False):
        reason = state.get("reason") or "license_invalid"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"license_revoked:{reason}",
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
        raise HTTPException(
            status_code=400, detail="last_message_must_be_user"
        )
    _assert_license_ok()

    admin_email = admin["sub"]
    tenant = _resolve_tenant(admin_email)
    last_user_content = body.messages[-1].content

    # BUG-40 — multi-turn chat history. Pre-fix the handler persisted
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
        new_msgs = body.messages[existing_count:] if existing_count else list(body.messages)
        for m in new_msgs:
            db.add(
                ChatMessage(
                    session_id=sess_id,
                    role=m.role,
                    content=m.content,
                )
            )
        # Q12 / Brief 3 R4 — bump the sidebar denorm columns. The
        # assistant-message branch later adds another +1 on its own
        # commit, so user + assistant each contribute one.
        sess.last_activity_at = datetime.now(timezone.utc)
        sess.message_count = (sess.message_count or 0) + len(new_msgs)
        db.add(sess)
        db.commit()

    cmd = _detect_slash_command(last_user_content)

    # Q12 / Brief 3 R2 — pipeline routing decision (auto / explicit).
    if body.pipeline == "auto":
        pipeline_used = detect_pipeline(last_user_content)
    else:
        pipeline_used = body.pipeline

    # Sprint 2N FAZ E (P1 #2M-018) — pre-flight provider probe.
    # Sprint 2M repro: 6 provider hepsi devre dışıyken /v1/chat/completions
    # HTTP 200 + SSE stream başlatıyor, içinde Türkçe error text yield.
    # JS client `response.ok = true` görüp retry semantics kaybediyor.
    # Stream başlatmadan ÖNCE active provider sayısı 0 ise structured
    # 503 JSON dön → fetch().ok=false, retry/Retry-After mantığı doğru.
    #
    # Skip when:
    #   - qual_* pipeline (kendi orchestration'ını yapar)
    #   - Anthropic mock provider active (test/dev path; _try_mock
    #     stream içinde yine çalışır)
    if (
        body.pipeline in ("auto", "cascade")
        and pipeline_used not in ("qual_code", "qual_tr", "qual_analysis", "qual_translate")
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
                        "hint": "/admin/settings → Providers'ta en az bir API anahtarı yapılandırın.",
                    },
                    headers={"Retry-After": "60"},
                )

    async def stream() -> AsyncGenerator[str, None]:
        yield f'data: {json.dumps({"type": "session", "session_id": sess_id, "title": sess_title})}\n\n'
        yield f'data: {json.dumps({"type": "pipeline", "id": pipeline_used})}\n\n'

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

        # Q12 / Brief 3 R1 — RAG-grounded citations: pull top-K chunks
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
                yield f'data: {json.dumps({"type": "citations", "citations": serialise_citations(citations)})}\n\n'

        # BUG-40 — multi-turn rendering. Build a "User: …\nAssistant: …"
        # transcript from body.messages and append the citation-augmented
        # last user line. Single-turn requests (one user msg) collapse
        # to the previous behaviour: just the user content + citations.
        if len(body.messages) > 1:
            history_lines: list[str] = []
            for m in body.messages[:-1]:
                role_label = "User" if m.role == "user" else (
                    "Assistant" if m.role == "assistant" else m.role.capitalize()
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

        # Q11-L10-002: emit a "thinking" frame before the cascade call
        # so the client (and any intermediate proxy / load balancer) sees
        # SSE traffic well within the 30s idle-timeout window. Live
        # provider calls can run 5-30s; without this beat a slow
        # provider would silently disconnect mid-request.
        yield f'data: {json.dumps({"type": "thinking"})}\n\n'

        t0 = time.perf_counter()
        # Sprint 2C ITEM-3 — qual_* dedicated multi-model pipelines.
        from app.pipelines.qual import QUAL_HANDLERS as _QUAL_HANDLERS
        from app.pipelines.qual import run_qual_pipeline as _run_qual

        qual_meta: Optional[Dict] = None
        try:
            if pipeline_used in _QUAL_HANDLERS:
                qual_result = await _run_qual(pipeline_used, prompt_for_cascade)
                qual_meta = qual_result.to_dict()
                cascade_resp = CascadeResponse(
                    completion=qual_result.completion or "",
                    provider=(qual_result.providers[-1] if qual_result.providers else "qual"),
                    fallback_chain=list(qual_result.providers) or ["qual"],
                    tokens_used=0,
                    mock=False,
                    cached=False,
                    elapsed_ms=qual_result.elapsed_ms,
                    model=pipeline_used,
                )
            else:
                cascade_resp = await _run_cascade(prompt_for_cascade)
        except HTTPException as exc:
            detail_str = str(exc.detail or "")
            if detail_str.startswith("no_providers_configured"):
                err_text = (
                    "Henüz sağlayıcı yapılandırılmadı. "
                    "/admin/settings → Providers."
                )
            elif detail_str.startswith("no_free_providers_configured"):
                err_text = (
                    "Ücretsiz sağlayıcı yapılandırılmadı "
                    "(skip_paid aktif)."
                )
            elif detail_str.startswith("all_providers_failed"):
                err_text = (
                    "Tüm sağlayıcılar geçici hata verdi; "
                    "lütfen tekrar deneyin."
                )
            else:
                err_text = "Cascade canlı uçları henüz aktif değil."
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
                    now = datetime.now(timezone.utc)
                    touched.updated_at = now
                    # Q12 / Brief 3 R4 — keep the sidebar-sort denorm
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
                "content": text[i:i + chunk_size],
                "provider": provider,
            }
            yield f'data: {json.dumps(payload)}\n\n'
            await asyncio.sleep(0.01)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        # Q12 / Brief 3 R5 — provider transparency: emit cost USD +
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
        yield f'data: {json.dumps(meta)}\n\n'
        yield 'data: [DONE]\n\n'

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
