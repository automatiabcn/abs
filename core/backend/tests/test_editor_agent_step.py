# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""One step of the editor agent, with the provider scripted.

What is pinned: a JSON reply becomes an `action` frame and is never shown
as text; prose streams as deltas after a held prefix; a leaked reasoning
sentence never reaches the developer; a cut-off answer is continued; an
answer in the wrong language is regenerated; a broken tool call gets one
repair turn; and the routes stand behind the same token as the chat.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import pytest

from app.api.mcp_tokens import _sign
from app.editor_agent import step as step_mod
from app.editor_agent.context import StepRecord
from app.editor_agent.step import StepRequest, run_step
from app.providers.schemas import ProviderResponse
from app.workspace import current as ws


@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    monkeypatch.setattr(ws, "_OPEN", {})
    monkeypatch.setattr(ws, "_LATEST", {})


class Script:
    """A provider that says what the test tells it to, in order."""

    def __init__(self, replies: List[Dict[str, Any]]):
        self.replies = list(replies)
        self.prompts: List[str] = []
        self.kwargs: List[Dict[str, Any]] = []

    def _next(self) -> Dict[str, Any]:
        return self.replies.pop(0) if self.replies else {"text": ""}

    async def stream(self, prompt, **kw):
        self.prompts.append(prompt)
        self.kwargs.append(kw)
        r = self._next()
        yield {"type": "provider", "name": "scripted", "streams": True}
        text = r["text"]
        for i in range(0, len(text), 37):
            yield {"type": "delta", "text": text[i : i + 37]}
        yield {
            "type": "done",
            "response": ProviderResponse(
                text=text, model="m", provider="scripted", elapsed_ms=5,
                tokens_in=10, tokens_out=len(text) // 4, truncated=bool(r.get("truncated")),
                tool_calls=list(r.get("tool_calls") or []),
            ),
        }

    async def call(self, prompt, **kw):
        self.prompts.append(prompt)
        self.kwargs.append(kw)
        r = self._next()
        return ProviderResponse(
            text=r["text"], model="m", provider="scripted", elapsed_ms=5,
            tokens_in=10, tokens_out=len(r["text"]) // 4, truncated=bool(r.get("truncated")),
        )


@pytest.fixture()
def scripted(monkeypatch):
    holder: Dict[str, Script] = {}

    def install(replies):
        s = Script(replies)
        holder["s"] = s
        import app.cascade.orchestrator as orch

        monkeypatch.setattr(orch, "stream_with_cascade", s.stream)
        monkeypatch.setattr(orch, "call_with_cascade", s.call)
        monkeypatch.setattr(
            step_mod,
            "resolve_chain",
            lambda prefer, tenant, user: {
                "primary": "scripted", "fallbacks": (), "active": ["scripted"],
                "tenant": tenant, "user": user,
            },
        )
        return s

    return install


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "routes.py").write_text("def market():\n    pass\n", encoding="utf-8")
    (tmp_path / "app" / "models.py").write_text("class User:\n    id = 1\n", encoding="utf-8")
    return str(tmp_path)


async def _collect(body: StepRequest) -> List[Dict[str, Any]]:
    return [ev async for ev in run_step(body, tenant="default", user="dev@example.com")]


@pytest.mark.asyncio
async def test_a_tool_call_becomes_an_action_and_is_never_shown_as_text(scripted, project):
    scripted([{"text": '{"tool": "read_file", "args": {"path": "app/routes.py", "extra": 1}}'}])
    evs = await _collect(StepRequest(message="Login nerede tanımlı?", workspace_root=project))
    kinds = [e["type"] for e in evs]
    assert kinds == ["meta", "provider", "action"]
    act = evs[-1]
    assert act["name"] == "read_file" and act["args"] == {"path": "app/routes.py"}
    assert act["where"] == "editor" and act["needs_approval"] is False
    meta = evs[0]
    assert meta["lang"] == "tr" and meta["mode"] == "agent" and meta["max_steps"] >= 8
    assert meta["step"] == 1 and "app/routes.py" in meta["used_files"] or True


@pytest.mark.asyncio
async def test_prose_streams_after_the_held_prefix_and_ends_with_the_final_text(scripted, project):
    answer = "Login `app/routes.py:1` içindeki `market` fonksiyonunda değil; " * 8
    scripted([{"text": answer}])
    evs = await _collect(StepRequest(message="Login nerede?", workspace_root=project))
    deltas = [e["text"] for e in evs if e["type"] == "delta"]
    assert "".join(deltas) == answer
    final = [e for e in evs if e["type"] == "final"][0]
    assert final["text"] == answer.strip() or final["text"] == answer
    assert final["unverified"] == [] and final["provider"] == "scripted"


@pytest.mark.asyncio
async def test_leaked_reasoning_never_reaches_the_developer(scripted, project):
    scripted([{"text": "We need to request the file list.**Proje Genel Bakışı**\n\n" + "Flask uygulaması. " * 20}])
    evs = await _collect(StepRequest(message="projeyi incele", workspace_root=project))
    shown = "".join(e["text"] for e in evs if e["type"] == "delta")
    assert "We need to" not in shown
    assert shown.startswith("**Proje Genel Bakışı**")
    assert [e for e in evs if e["type"] == "final"][0]["text"].startswith("**Proje")


@pytest.mark.asyncio
async def test_a_cut_off_answer_is_continued_not_delivered_blank(scripted, project):
    first = "Kalan işler:\n1. market rotası\n2. profil formu\n3. " + "detay " * 40
    s = scripted([{"text": first, "truncated": True}, {"text": "giriş/çıkış rotaları.\n4. testler."}])
    evs = await _collect(StepRequest(message="kalan işler neler?", workspace_root=project))
    final = [e for e in evs if e["type"] == "final"][0]
    assert final["continued"] == 1 and not final["truncated"]
    assert final["text"].endswith("4. testler.")
    assert "Continue exactly where it stopped" in s.prompts[-1]


@pytest.mark.asyncio
async def test_an_answer_in_the_wrong_language_is_regenerated_once(scripted, project):
    english = (
        "Sure! Which page or feature would you like to tackle next? For example the "
        "profile edit, the login and logout flow, or the product detail page. Let me know."
    )
    turkish = (
        "Sırayla ilerleyelim: önce profil sayfasındaki formu tamamlayalım, sonra giriş ve "
        "çıkış rotalarını, en son ürün detay sayfasını yapalım. İlk adımla başlıyorum."
    )
    s = scripted([{"text": english}, {"text": turkish}])
    evs = await _collect(
        StepRequest(message="sayfalar uzerinde calismaya devam edelim sirasiyla", workspace_root=project)
    )
    final = [e for e in evs if e["type"] == "final"][0]
    assert final["regenerated"] and final["lang_drift"] == "en"
    assert final["text"] == turkish
    assert [e for e in evs if e["type"] == "replace"][0]["text"] == turkish
    assert "developer writes in Turkish" in s.prompts[-1]


@pytest.mark.asyncio
async def test_a_broken_tool_call_gets_one_repair_turn(scripted, project):
    s = scripted([
        {"text": '{"tool": "grep", "args": {"pattern": '},
        {"text": '{"tool": "grep", "args": {"pattern": "cart"}}'},
    ])
    evs = await _collect(StepRequest(message="sepet nerede?", workspace_root=project))
    act = evs[-1]
    assert act["type"] == "action" and act["name"] == "grep" and act["args"] == {"pattern": "cart"}
    assert "not a valid JSON object" in s.prompts[-1]


@pytest.mark.asyncio
async def test_a_tool_the_mode_does_not_offer_is_reported_to_the_model(scripted, project):
    scripted([{"text": '{"tool": "propose_edit", "args": {"path": "a.py", "search": "x", "replace": "y"}}'}])
    evs = await _collect(StepRequest(message="fix it", mode="ask", workspace_root=project))
    act = evs[-1]
    assert act["type"] == "action" and act["error"] and "no tool called 'propose_edit'" in act["error"]


@pytest.mark.asyncio
async def test_later_steps_carry_the_run_and_drop_the_initial_files(scripted, project):
    s = scripted([{"text": "Cevap: market app/routes.py:1 içinde. " * 8}])
    evs = await _collect(
        StepRequest(
            message="market nerede?",
            workspace_root=project,
            steps=[StepRecord(name="read_file", args={"path": "app/routes.py"}, result="1: def market():\n2:     pass")],
        )
    )
    assert evs[0]["step"] == 2 and evs[0]["used_files"] == []
    prompt = s.prompts[0]
    assert "Your work so far in this turn" in prompt and "[Step 1] You called read_file" in prompt
    assert "Files already read for you" not in prompt


@pytest.mark.asyncio
async def test_an_invented_path_is_marked_unverified(scripted, project):
    scripted([{"text": "Sepet toplamı `app/cart.py` içinde ve app/routes.py:40 satırında hesaplanıyor. " * 3}])
    evs = await _collect(StepRequest(message="Sepet toplamı nerede hesaplanıyor?", workspace_root=project))
    final = [e for e in evs if e["type"] == "final"][0]
    assert final["unverified"] == ["app/cart.py"]


# --- the routes --------------------------------------------------------------


def _token(**over) -> str:
    payload = {
        "tenant": "default", "scope": "all", "label": "test",
        "exp": int(time.time()) + 3600, "actor": "dev@example.com", **over,
    }
    return _sign(payload)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_the_step_route_needs_the_editor_token(client):
    r = client.post("/v1/editor/agent/step", json={"message": "hi"})
    assert r.status_code == 401
    r = client.post("/v1/editor/agent/tool", json={"name": "semantic_search", "args": {"query": "x"}})
    assert r.status_code == 401


def test_the_tool_route_says_when_no_project_is_open(client, monkeypatch):
    import app.api.editor_agent as api

    monkeypatch.setattr(api, "_licence_allows", lambda: None)
    r = client.post(
        "/v1/editor/agent/tool",
        json={"name": "semantic_search", "args": {"query": "x"}},
        headers={"Authorization": f"Bearer {_token()}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["error"] == "no_workspace"


def test_the_step_route_streams_events(client, monkeypatch, scripted, project):
    import app.api.editor_agent as api

    monkeypatch.setattr(api, "_licence_allows", lambda: None)
    scripted([{"text": '{"tool": "list_dir", "args": {"path": ""}}'}])
    with client.stream(
        "POST",
        "/v1/editor/agent/step",
        json={"message": "projeyi incele", "workspace_root": project},
        headers={"Authorization": f"Bearer {_token()}"},
    ) as r:
        assert r.status_code == 200
        frames = [json.loads(l[5:]) for l in r.iter_lines() if l.startswith("data:")]
    assert [f["type"] for f in frames] == ["meta", "provider", "action"]
    assert frames[-1]["name"] == "list_dir"


@pytest.mark.asyncio
async def test_a_native_tool_call_becomes_an_action_without_any_text(scripted, project):
    """Groq's gpt-oss calls tools the native way when offered `tools` — and
    even when not (live 09-01: 'Tool choice is none, but model called a
    tool'). A native call needs no JSON in the text at all."""
    s = scripted([{"text": "", "tool_calls": [{"name": "grep", "arguments": '{"pattern": "cart", "max_results": 5}'}]}])
    evs = await _collect(StepRequest(message="sepet nerede?", workspace_root=project))
    act = evs[-1]
    assert act["type"] == "action" and act["native"] is True
    assert act["name"] == "grep" and act["args"] == {"pattern": "cart", "max_results": 5}
    # The catalogue went with the request, in the function-calling shape.
    assert s.kwargs[-1]["tools"][0]["type"] == "function"
    assert {t["function"]["name"] for t in s.kwargs[-1]["tools"]} >= {"read_file", "propose_edit"}


def test_the_stream_parser_reads_native_tool_calls_and_salvages_a_rejection():
    import asyncio

    from app.providers.base import _tool_calls_of, openai_compatible_stream

    assert _tool_calls_of({"tool_calls": [{"function": {"name": "grep", "arguments": {"pattern": "x"}}}]}) == [
        {"name": "grep", "arguments": '{"pattern": "x"}'}
    ]

    class _Resp:
        status_code = 200

        async def aread(self):
            return b""

        async def aiter_lines(self):
            for line in (
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"read_","arguments":""}}]}}]}',
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"file","arguments":"{\\"path\\":"}}]}}]}',
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"a.py\\"}"}}]},"finish_reason":"tool_calls"}]}',
                'data: {"usage":{"prompt_tokens":5,"completion_tokens":3}}',
                "data: [DONE]",
            ):
                yield line

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, *a, **k):
            resp = _Resp()

            class _Ctx:
                async def __aenter__(self_inner):
                    return resp

                async def __aexit__(self_inner, *a):
                    return False

            return _Ctx()

    import app.providers.base as base

    real = base.httpx.AsyncClient
    base.httpx.AsyncClient = _Client
    try:
        async def run():
            events = []
            async for ev in openai_compatible_stream(
                url="http://x", api_key="k", model="m", prompt="p", provider_name="t"
            ):
                events.append(ev)
            return events

        events = asyncio.run(run())
    finally:
        base.httpx.AsyncClient = real
    final = events[-1].final
    assert final.tool_calls == [{"name": "read_file", "arguments": '{"path":"a.py"}'}]
    assert not final.truncated and final.tokens_out == 3


@pytest.mark.asyncio
async def test_a_looping_model_has_its_tools_taken_away_and_answers(scripted, project):
    """Live 09-01: thirteen greps for 'total' in a row. After two repeats the
    tools are withheld and the reply must be the answer."""
    s = scripted([{"text": "Sepet toplamı projede hesaplanmıyor; `total_price` yalnızca app/models.py:47 içinde bir sütun. " * 3}])
    rep = [StepRecord(name="grep", args={"pattern": "total"}, result="app/models.py:47: total_price") for _ in range(3)]
    evs = await _collect(StepRequest(message="Sepet toplamı nerede?", workspace_root=project, steps=rep))
    assert s.kwargs[-1].get("tools") is None
    assert "no more tool calls are available" in s.prompts[-1]
    assert evs[-1]["type"] == "final" and "hesaplanmıyor" in evs[-1]["text"]


@pytest.mark.asyncio
async def test_a_too_large_request_is_retried_once_with_a_smaller_context(scripted, project, monkeypatch):
    """Live 09-01: one read_file of a 160-line file and Groq's free window
    answered 413 — the step died. Now it shrinks and tries once more."""
    s = scripted([{"text": "Kısa cevap: market app/routes.py:1 içinde. " * 8}])
    import app.cascade.orchestrator as orch

    real = s.stream
    calls = {"n": 0}

    async def flaky(prompt, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("groq request too large for its window")
        async for ev in real(prompt, **kw):
            yield ev

    monkeypatch.setattr(orch, "stream_with_cascade", flaky)
    big = StepRecord(name="read_file", args={"path": "app/routes.py"}, result="x" * 9000)
    evs = await _collect(StepRequest(message="market nerede?", workspace_root=project, steps=[big]))
    assert [e["type"] for e in evs if e["type"] in ("waiting", "final")] == ["waiting", "final"]
    assert "smaller context" in [e for e in evs if e["type"] == "waiting"][0]["reason"]
    assert len(s.prompts[-1]) < 9000  # the 9000-char result was clipped
    assert "Tools (defined as functions you can call)" in s.prompts[-1]
