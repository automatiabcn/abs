# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Plain chat used to send the user's words to the provider and nothing else.

No system prompt at all — so the model answered as whatever generic assistant its
provider had trained, with no idea what it was or where it was running. Asked
"can you check this server's status?" in the panel *of that very server*, with a
real Groq key, it replied:

    "I'm not capable of directly accessing or checking the status of a specific
     server. However, I can guide you... Use online tools: UptimeRobot,
     DownDetector..."

That is the product denying, to the customer who installed it, the one thing it
is for. With the preamble it now says: "Agent mode is currently off... for
detailed server status, switch Agent mode on in the composer" — which is a button
six inches below the answer.

The failure was silent: nothing errored, no test went red, the model simply
answered like a stranger. So this asserts the preamble on the prompt that
actually reaches the cascade, not on a string built inside the test.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_mod
from app.api.chat import ASSISTANT_PREAMBLE
from app.main import app


@pytest.fixture
def client(monkeypatch):
    async def fake_admin():
        return {"sub": "admin@preamble.local", "tnt": "default", "roles": ["admin"]}

    app.dependency_overrides[chat_mod.current_admin] = fake_admin

    from app.api.cascade import CascadeResponse

    captured: dict[str, Any] = {"prompt": None}

    async def fake_run_cascade(prompt: str, max_tokens: int = 1024, **kw: Any):
        captured["prompt"] = prompt
        return CascadeResponse(
            completion="ok",
            provider="mock",
            fallback_chain=[],
            tokens_used=1,
            mock=True,
        )

    async def empty_citations(*a, **kw):
        return []

    monkeypatch.setattr(chat_mod, "_run_cascade", fake_run_cascade)
    monkeypatch.setattr(chat_mod, "_assert_license_ok", lambda: None)
    monkeypatch.setattr(chat_mod, "get_active_providers", lambda **_: ["groq"])
    monkeypatch.setattr(chat_mod, "retrieve_citations", empty_citations)

    yield TestClient(app), captured

    app.dependency_overrides.clear()


def test_the_preamble_says_where_it_runs_and_what_to_do_instead():
    text = ASSISTANT_PREAMBLE.lower()
    assert "own server" in text
    assert "agent mode" in text


def test_the_prompt_that_reaches_the_provider_says_what_the_assistant_is(client):
    c, captured = client
    r = c.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "Can you check this server?"}],
            "rag_citations": False,
        },
    )
    assert r.status_code == 200, r.text

    prompt = captured["prompt"]
    assert prompt is not None, "the cascade was never called"
    assert prompt.startswith("You are ABS"), prompt[:120]
    assert "Agent mode" in prompt
    # ...and the customer's own question survives the preamble.
    assert "Can you check this server?" in prompt


def test_it_is_there_on_a_follow_up_turn_too(client):
    c, captured = client
    r = c.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
                {"role": "user", "content": "and now?"},
            ],
            "rag_citations": False,
        },
    )
    assert r.status_code == 200, r.text
    assert captured["prompt"].startswith("You are ABS")
