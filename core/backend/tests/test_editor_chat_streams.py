# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The editor chat arrives as it is produced.

Until 2026-08-28 the developer looked at "Thinking…" for the whole of the
provider's time and then read a finished answer. These tests pin the
streaming path end to end: the provider stream parser, the cascade's
fail-over rule (before the first word: next provider, silently; after it:
say so and keep what was said), and the route that carries it to the
editor behind the same token and licence gate as the tools.
"""

from __future__ import annotations

import json
import time
from typing import List

import pytest

from app.api.mcp_tokens import _sign
from app.providers.base import BaseProvider, StreamEvent, parse_openai_stream_line
from app.providers.schemas import ProviderError, ProviderResponse
from app.workspace import current as ws


@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    monkeypatch.setattr(ws, "_OPEN", {})
    monkeypatch.setattr(ws, "_LATEST", {})


def _token(**over) -> str:
    payload = {
        "tenant": "default",
        "scope": "all",
        "label": "test",
        "exp": int(time.time()) + 3600,
        "actor": "dev@example.com",
        **over,
    }
    return _sign(payload)


# --- provider stream parsing ---------------------------------------------


def test_stream_lines_that_are_not_data_are_ignored():
    assert parse_openai_stream_line("") is None
    assert parse_openai_stream_line(": keep-alive") is None
    assert parse_openai_stream_line("data: [DONE]") is None
    assert parse_openai_stream_line("data: not json") is None
    assert parse_openai_stream_line('data: {"choices": []}') == {"choices": []}


# --- fakes -------------------------------------------------------------


class _Streamer(BaseProvider):
    """Says its pieces, then reports usage — like a real streaming leg."""

    name = "streamer"
    default_model = "m1"
    streams = True

    def __init__(self, pieces: List[str], fail_after: int | None = None, name: str = "streamer"):
        self.pieces = pieces
        self.fail_after = fail_after
        self.name = name

    async def call(self, prompt, model=None, **kw):  # pragma: no cover
        raise AssertionError("the streaming path must not fall back to call()")

    async def stream(self, prompt, model=None, **kw):
        for i, p in enumerate(self.pieces):
            if self.fail_after is not None and i == self.fail_after:
                raise ProviderError("wire dropped", provider=self.name, transient=True)
            yield StreamEvent(delta=p)
        yield StreamEvent(
            final=ProviderResponse(
                text="".join(self.pieces), model=model or self.default_model,
                provider=self.name, tokens_in=3, tokens_out=len(self.pieces),
            )
        )


class _Dead(BaseProvider):
    """Fails before saying anything — the case the cascade must hide."""

    name = "dead"
    default_model = "m0"

    async def call(self, prompt, model=None, **kw):
        raise ProviderError("no key", provider=self.name, transient=False)


class _Blocking(BaseProvider):
    """A provider without streaming still answers through stream()."""

    name = "blocking"
    default_model = "m2"

    async def call(self, prompt, model=None, **kw):
        return ProviderResponse(text="whole answer", model="m2", provider=self.name)


def _wire(monkeypatch, providers):
    from app.cascade import orchestrator as orch

    table = {p.name: p for p in providers}
    monkeypatch.setattr(orch, "get_provider", lambda name: table[name])
    monkeypatch.setattr(orch, "_resolve_owner_key", lambda *a, **k: None)


async def _collect(gen):
    return [ev async for ev in gen]


# --- the cascade, streamed ---------------------------------------------


@pytest.mark.asyncio
async def test_pieces_arrive_in_order_and_the_books_are_kept(monkeypatch):
    from app.cascade.orchestrator import stream_with_cascade

    _wire(monkeypatch, [_Streamer(["Hel", "lo", " world"])])
    events = await _collect(
        stream_with_cascade("q", primary="streamer", use_cache=False, tenant_id="t")
    )
    kinds = [e["type"] for e in events]
    assert kinds == ["provider", "delta", "delta", "delta", "done"]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Hello world"
    done = events[-1]["response"]
    assert done.text == "Hello world"
    assert done.providers_tried == ["streamer"]
    assert done.tokens_out == 3


@pytest.mark.asyncio
async def test_a_provider_that_fails_before_speaking_is_never_seen(monkeypatch):
    from app.cascade.orchestrator import stream_with_cascade

    _wire(monkeypatch, [_Dead(), _Streamer(["ok"])])
    events = await _collect(
        stream_with_cascade(
            "q", primary="dead", fallbacks=("streamer",), use_cache=False, tenant_id="t"
        )
    )
    # The dead leg is announced (the panel shows the trail) but produces no
    # text and no error; the answer comes whole from the next provider.
    assert [e["type"] for e in events] == ["provider", "leg_failed", "provider", "delta", "done"]
    assert events[1]["name"] == "dead" and "no key" in events[1]["detail"]
    assert events[-1]["response"].providers_tried == ["dead", "streamer"]


@pytest.mark.asyncio
async def test_a_provider_that_fails_mid_answer_says_so_and_keeps_the_words(monkeypatch):
    from app.cascade.orchestrator import stream_with_cascade

    _wire(
        monkeypatch,
        [_Streamer(["one ", "two ", "three"], fail_after=2), _Streamer(["never"], name="second")],
    )
    events = await _collect(
        stream_with_cascade(
            "q", primary="streamer", fallbacks=("second",), use_cache=False, tenant_id="t"
        )
    )
    assert events[-1]["type"] == "error"
    assert events[-1]["partial"] == "one two "
    # No second answer under the half one.
    assert "never" not in json.dumps([e for e in events if e["type"] == "delta"])


@pytest.mark.asyncio
async def test_a_provider_without_streaming_still_answers_whole(monkeypatch):
    from app.cascade.orchestrator import stream_with_cascade

    _wire(monkeypatch, [_Blocking()])
    events = await _collect(
        stream_with_cascade("q", primary="blocking", use_cache=False, tenant_id="t")
    )
    assert events[0] == {"type": "provider", "name": "blocking", "streams": False}
    assert [e["type"] for e in events] == ["provider", "delta", "done"]
    assert events[1]["text"] == "whole answer"


@pytest.mark.asyncio
async def test_every_provider_dead_raises_like_the_blocking_cascade(monkeypatch):
    from app.cascade.orchestrator import stream_with_cascade

    _wire(monkeypatch, [_Dead()])
    with pytest.raises(ProviderError):
        await _collect(stream_with_cascade("q", primary="dead", use_cache=False, tenant_id="t"))


# --- the route ----------------------------------------------------------


def _frames(text: str) -> list:
    return [
        json.loads(line[len("data:"):])
        for line in text.splitlines()
        if line.startswith("data:")
    ]


def test_the_route_needs_the_editor_token(client):
    r = client.post("/v1/editor/chat/stream", json={"prompt": "hi"})
    assert r.status_code == 401
    r = client.post(
        "/v1/editor/chat/stream",
        json={"prompt": "hi"},
        headers={"Authorization": f"Bearer {_token(scope='hooks')}"},
    )
    assert r.status_code == 403


def test_the_route_streams_the_answer_with_its_provenance(client, monkeypatch, tmp_path):
    from app.mcp.tools import engine_panel_tools as ept

    (tmp_path / "billing.py").write_text("def vat(x):\n    return x * 0.21\n")
    _wire(monkeypatch, [_Streamer(["It ", "is ", "21%."])])
    monkeypatch.setattr(ept, "get_active_providers", lambda **k: ["streamer"], raising=False)
    monkeypatch.setattr("app.providers.cascade.get_active_providers", lambda **k: ["streamer"])

    with client.stream(
        "POST",
        "/v1/editor/chat/stream",
        json={"prompt": "what is the vat?", "workspace_root": str(tmp_path), "use_cache": False},
        headers={"Authorization": f"Bearer {_token()}"},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        frames = _frames("".join(r.iter_text()))

    kinds = [f["type"] for f in frames]
    assert kinds[0] == "meta"
    assert frames[0]["used_files"] == ["billing.py"]
    assert kinds[-1] == "done"
    assert "".join(f["text"] for f in frames if f["type"] == "delta") == "It is 21%."
    assert frames[-1]["provider"] == "streamer"
    assert frames[-1]["providers_tried"] == ["streamer"]
    assert frames[-1]["used_files"] == ["billing.py"]


def test_the_route_is_behind_the_licence_gate(client, monkeypatch):
    monkeypatch.setattr(
        "app.mcp.gate._gate_status", lambda: {"allowed": False, "detail": "lapsed"}
    )
    r = client.post(
        "/v1/editor/chat/stream",
        json={"prompt": "hi"},
        headers={"Authorization": f"Bearer {_token()}"},
    )
    frames = _frames(r.text)
    assert frames == [{"type": "error", "error": "subscription_required", "detail": "lapsed"}]


# --- the other streaming providers' event shapes ---------------------


def test_gemini_and_cloudflare_stream_pieces_are_read_correctly():
    from app.providers.cloudflare import cloudflare_stream_piece
    from app.providers.gemini.adapter import gemini_stream_piece

    assert gemini_stream_piece(
        {"candidates": [{"content": {"parts": [{"text": "Mer"}, {"text": "haba"}]}}]}
    ) == ("Merhaba", None)
    assert gemini_stream_piece(
        {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}
    ) == ("", "MAX_TOKENS")
    assert gemini_stream_piece({"usageMetadata": {"promptTokenCount": 3}}) == ("", None)
    assert cloudflare_stream_piece({"response": "hi"}) == "hi"
    assert cloudflare_stream_piece({"choices": [{"delta": {"content": "yo"}}]}) == "yo"
    assert cloudflare_stream_piece({"response": None}) == ""


def test_every_cloud_provider_in_the_default_chain_streams():
    """The point of the stream is the first provider that answers. A chain
    whose head cannot stream hands the developer a one-piece answer with a
    cursor in front of it."""
    from app.providers.registry import get_provider

    for name in ("groq", "cerebras", "gemini", "cloudflare"):
        assert get_provider(name).streams, name


def test_an_attached_diff_is_redacted_like_a_file(client, monkeypatch):
    """A git diff of a .env is still a .env."""
    from app.mcp.tools import engine_panel_tools as ept

    seen = {}

    def fake_prepare(prompt, **kw):
        seen.update(kw)
        return {"error": {"ok": False, "error": "stop_here", "detail": ""}}

    monkeypatch.setattr(ept, "prepare_chat_ask", fake_prepare)
    r = client.post(
        "/v1/editor/chat/stream",
        json={"prompt": "hi", "attachments": "+GROQ_API_KEY=gsk_abcdefghijklmnopqrstuvwxyz123456"},
        headers={"Authorization": f"Bearer {_token()}"},
    )
    assert r.status_code == 200
    assert "gsk_abcdefghijklmnopqrstuvwxyz123456" not in seen["attachments"]


@pytest.mark.asyncio
async def test_stopping_the_consumer_closes_the_provider_stream(monkeypatch):
    """Stop must reach the provider: a generator the client walked away from
    is closed, so the HTTP stream behind it is closed too — not left reading
    tokens nobody will see (and paying for them)."""
    from app.cascade.orchestrator import stream_with_cascade

    closed = {"provider": False}

    class _Slow(BaseProvider):
        name = "slow"
        default_model = "m"
        streams = True

        async def call(self, prompt, model=None, **kw):  # pragma: no cover
            raise AssertionError

        async def stream(self, prompt, model=None, **kw):
            try:
                for i in range(1000):
                    yield StreamEvent(delta=f"w{i} ")
            finally:
                closed["provider"] = True

    _wire(monkeypatch, [_Slow()])
    gen = stream_with_cascade("q", primary="slow", use_cache=False, tenant_id="t")
    got = 0
    async for ev in gen:
        if ev["type"] == "delta":
            got += 1
        if got == 3:
            break
    await gen.aclose()
    assert closed["provider"] is True
