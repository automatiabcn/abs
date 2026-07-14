"""033 Modul C — Provider mock layer (deterministic responses)."""

from __future__ import annotations

import asyncio


def test_mock_openai_chat_returns_provider_response():
    from app.providers.mock import mock_openai_chat
    from app.providers.schemas import ProviderResponse

    r = asyncio.run(mock_openai_chat("groq/compound", "hello world"))
    assert isinstance(r, ProviderResponse)
    assert r.provider == "mock"
    assert "[mock:groq/compound]" in (r.text or "")
    assert (r.tokens_in or 0) >= 1


def test_mock_anthropic_message_uses_higher_latency_band():
    """Should still return a ProviderResponse text within 5s wall clock."""
    import time

    from app.providers.mock import mock_anthropic_message

    t0 = time.monotonic()
    r = asyncio.run(mock_anthropic_message("claude-sonnet-4-7", "hi"))
    elapsed_ms = (time.monotonic() - t0) * 1000
    assert r.text.startswith("[mock:claude-sonnet-4-7]")
    assert elapsed_ms < 5000


def test_mock_stripe_event_shape():
    from app.providers.mock import mock_stripe_event

    e = mock_stripe_event("checkout.session.completed")
    assert e["object"] == "event"
    assert e["type"] == "checkout.session.completed"
    assert e["livemode"] is False
    assert e["data"]["object"]["customer_email"] == "demo@meetingco.test"


def test_mock_github_oauth_and_slack_post():
    from app.providers.mock import mock_github_oauth_token, mock_slack_post

    tok = mock_github_oauth_token("0123456789abcdef")
    assert tok["access_token"].startswith("ghs_mock_")
    assert tok["token_type"] == "bearer"

    msg = mock_slack_post("#demo", "test")
    assert msg["ok"] is True
    assert msg["channel"] == "#demo"
    assert msg["message"]["text"] == "test"


def test_mock_cohere_rerank_orders_by_length():
    from app.providers.mock import mock_cohere_rerank

    docs = ["short", "this is a much longer document", "medium length doc"]
    out = mock_cohere_rerank("q", docs)
    assert len(out) == 3
    # First entry should be the longest doc (index 1)
    assert out[0]["index"] == 1
