# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The cascade used to throw a web exception at callers who were not on the web.

When every provider failed for a reason that might pass — a rate limit, a
timeout — the cascade raised FastAPI's `HTTPException`. That is a fine thing to
raise inside a request handler. It is a terrible thing for a *library* to raise,
because the cascade is called by agents, MCP tools, pipelines and background
workers, none of which are behind an HTTP request, and every one of which was
catching `ProviderError` and nothing else.

So the one failure guaranteed to happen on a busy day walked straight through
their error handling:

  - agent mode died mid-stream on a rate limit (the connection was already open;
    the exception could not become a response, so the chat simply hung);
  - the "test this provider" button on the Providers page turned a busy provider
    into a raw 503 instead of "busy — try again";
  - MCP tools that handle a bad key gracefully did not handle a busy one at all.

It now raises `CascadeUnavailable`, which *is* a `ProviderError`. Everything that
already knew how to degrade, degrades. The HTTP surface is unchanged: an
exception handler builds the same 503, with the same body and the same
Retry-After.
"""

from __future__ import annotations

import pytest

from app.providers.schemas import CascadeUnavailable, ProviderError


def test_the_cascade_failure_is_catchable_as_a_provider_error():
    """The whole fix, in one line: it is a ProviderError."""
    exc = CascadeUnavailable("all down", providers_tried=["groq"])

    assert isinstance(exc, ProviderError)
    assert exc.transient is True, "a busy provider is not a broken one"


def test_a_caller_that_only_knows_provider_error_now_survives_a_busy_day():
    """This is what every MCP tool, agent and worker looks like. Before the
    change, this `except` did not fire and the exception escaped into a place
    that could not handle it."""
    caught = None
    try:
        raise CascadeUnavailable(
            "every provider was rate limited",
            providers_tried=["groq", "gemini"],
            last_error=ProviderError("429", provider="groq"),
        )
    except ProviderError as exc:  # the only clause these callers have
        caught = exc

    assert caught is not None, "a busy cascade escaped a ProviderError handler"


def test_testing_a_busy_provider_reports_busy_instead_of_exploding(client, monkeypatch):
    """The Providers page has a "test" button, and an operator uses it to decide
    whether their key works. A provider that is merely busy must come back as a
    readable failure — not as an unhandled 503 that reads, to the person clicking
    it, exactly like a broken key.

    Driven through the app, because that is how it is used: the route builds its
    own answer out of what the cascade raised, and before the fix the cascade
    raised something the route never caught.
    """
    from app.api.admin.auth import admin_required
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "groq_api_key", "gsk-test-key", raising=False)
    app.dependency_overrides[admin_required] = lambda: {"sub": "admin@local"}

    async def _busy(*a, **k):  # noqa: ANN001, ANN002
        raise CascadeUnavailable(
            "rate limited",
            providers_tried=["groq"],
            last_error=ProviderError("429 too many requests", provider="groq"),
        )

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _busy)

    try:
        resp = client.post("/v1/admin/providers/groq/test")
    finally:
        app.dependency_overrides.pop(admin_required, None)

    assert resp.status_code == 200, (
        "a busy provider crashed the test button instead of reporting itself busy"
    )
    body = resp.json()
    assert body["ok"] is False
    assert body["error"], "the operator was told nothing about why it failed"
