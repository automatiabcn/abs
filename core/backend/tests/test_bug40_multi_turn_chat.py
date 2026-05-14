# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""BUG-40 — chat.completions persists ALL new messages from
body.messages and forwards full conversation history to the cascade
orchestrator as a transcript.
"""

from __future__ import annotations

import json as _json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api import chat as chat_mod
from app.db.models import ChatMessage
from app.db.session import get_engine
from app.main import app


@pytest.fixture
def client(monkeypatch):
    async def fake_admin():
        return {"sub": "admin@phase2a.local", "tnt": "default", "roles": ["admin"]}

    app.dependency_overrides[chat_mod.current_admin] = fake_admin

    captured = {"prompt": None, "calls": 0}

    from app.api.cascade import CascadeResponse

    fake_resp = CascadeResponse(
        completion="ok",
        provider="mock",
        fallback_chain=[],
        tokens_used=10,
        mock=True,
    )

    async def fake_run_cascade(prompt: str, max_tokens: int = 1024, **kw: Any):
        captured["calls"] += 1
        captured["prompt"] = prompt
        return fake_resp

    monkeypatch.setattr(chat_mod, "_run_cascade", fake_run_cascade)
    monkeypatch.setattr(chat_mod, "_assert_license_ok", lambda: None)
    # Sprint 2N FAZ E (P1 #2M-018) — pre-flight provider probe gerektiriyor.
    # _run_cascade fake'lendiği için chat path provider olmadan çalışıyor;
    # probe'u memnun etmek için en az bir provider varmış gibi davran.
    monkeypatch.setattr(
        chat_mod,
        "get_active_providers",
        lambda **_: ["anthropic"],
    )

    async def empty_citations(*a, **kw):
        return []

    monkeypatch.setattr(chat_mod, "retrieve_citations", empty_citations)

    yield TestClient(app), captured

    app.dependency_overrides.clear()


def _post(c, messages, session_id=None):
    body = {"messages": messages, "rag_citations": False}
    if session_id:
        body["session_id"] = session_id
    return c.post("/v1/chat/completions", json=body)


def _sess_id_from_sse(text: str) -> str:
    m = re.search(r'"session_id":\s*"?([^",}]+)"?', text)
    assert m, text[:200]
    return m.group(1).strip()


def test_single_turn_prompt_has_no_history_prefixes(client):
    c, cap = client
    r = _post(c, [{"role": "user", "content": "hello"}])
    assert r.status_code == 200, r.text
    assert "User:" not in cap["prompt"]
    assert "Assistant:" not in cap["prompt"]
    assert "hello" in cap["prompt"]


def test_multi_turn_renders_history_in_prompt(client):
    c, cap = client
    r = _post(
        c,
        [
            {"role": "user", "content": "what is 2+2"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "and times 3?"},
        ],
    )
    assert r.status_code == 200, r.text
    p = cap["prompt"]
    assert "User: what is 2+2" in p
    assert "Assistant: 4" in p
    assert "and times 3?" in p
    assert p.rstrip().splitlines()[-1].endswith("and times 3?")


def test_multi_turn_persists_all_new_messages(client):
    c, _ = client
    r = _post(
        c,
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello!"},
            {"role": "user", "content": "second turn"},
        ],
    )
    assert r.status_code == 200
    sid = _sess_id_from_sse(r.text)

    with Session(get_engine()) as db:
        rows = list(
            db.exec(select(ChatMessage).where(ChatMessage.session_id == sid))
        )
    roles = [r.role for r in rows]
    contents = [r.content for r in rows]
    assert roles[:3] == ["user", "assistant", "user"]
    assert contents[:3] == ["hi", "hello!", "second turn"]
    assert "assistant" in roles[3:]


def test_resumed_session_only_persists_new_tail(client):
    c, _ = client
    r1 = _post(c, [{"role": "user", "content": "first"}])
    assert r1.status_code == 200
    sid = _sess_id_from_sse(r1.text)

    with Session(get_engine()) as db:
        before = list(
            db.exec(select(ChatMessage).where(ChatMessage.session_id == sid))
        )
    before_count = len(before)

    full_history = [{"role": r.role, "content": r.content} for r in before]
    full_history.append({"role": "user", "content": "second"})
    r2 = _post(c, full_history, session_id=sid)
    assert r2.status_code == 200, r2.text

    with Session(get_engine()) as db:
        after = list(
            db.exec(select(ChatMessage).where(ChatMessage.session_id == sid))
        )
    assert len(after) == before_count + 2
    assert after[-2].content == "second"
    assert after[-1].role == "assistant"
