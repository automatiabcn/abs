# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""JSON mode refusing the answer must not end the run.

Found by the effectiveness harness on its first real task, 2026-08-02: the
Composer asked for a change and produced nothing at all. `providers_tried` was
empty, `degraded` was true, and the server log said

    provider groq failed … 400 json_validate_failed
    "Failed to generate JSON. Please adjust your prompt."

The Composer sends `response_format={"type": "json_object"}`. When the model's
answer does not satisfy the provider's validator, the provider rejects the
whole call with a 400 — a permanent error — so the cascade moves on, and on a
free-tier install with one provider there is nowhere to move to. The developer
gets an empty proposal and no reason.

The strictness was never the point. `_parse` already strips fences and pulls
the first balanced object out of prose, precisely because models wrap JSON in
explanation. So a JSON-mode refusal is worth exactly one retry without the
flag: the same prompt, the same provider, the answer read the defensive way.

What is pinned here:

* a json-mode refusal is retried once, unstructured, and the run survives;
* the retry is not a general one. A quota error, a bad key, a timeout — those
  mean something else, and retrying them would double every real outage;
* one retry, not a loop. A provider that fails twice has answered.
"""

from __future__ import annotations

import pytest

from app.composer import runtime


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text
        self.provider = "groq"
        self.providers_tried = ["groq"]
        self.tokens_in = 10
        self.tokens_out = 20
        self.model = "openai/gpt-oss-120b"


_GOOD = '{"summary": "ok", "edits": [{"path": "a.py", "new_content": "x = 1\\n"}]}'


def _wire(monkeypatch, calls: list, *, first_error: Exception | None, then: str):
    async def _fake_cascade(prompt, **kwargs):  # noqa: ANN001
        calls.append(kwargs.get("response_format"))
        if len(calls) == 1 and first_error is not None:
            raise first_error
        return _Resp(then)

    monkeypatch.setattr(
        "app.cascade.orchestrator.call_with_cascade", _fake_cascade, raising=False
    )
    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers", lambda **_k: ["groq"]
    )


@pytest.mark.asyncio
async def test_a_json_mode_refusal_is_retried_without_it(monkeypatch):
    calls: list = []
    _wire(
        monkeypatch,
        calls,
        first_error=RuntimeError(
            'groq 400: {"error":{"code":"json_validate_failed",'
            '"message":"Failed to generate JSON. Please adjust your prompt."}}'
        ),
        then=_GOOD,
    )

    parsed, tried, _meta = await runtime._generate_edits(
        "make the picker honest", tenant_id="t", project_slug=None, user_subject=None
    )

    assert len(calls) == 2, "the run ended on the first refusal"
    assert calls[0] is not None, "the first attempt should still ask for JSON"
    assert calls[1] is None, "the retry has to drop the flag it failed on"
    assert parsed.get("edits"), "the developer still got an empty proposal"
    assert tried == ["groq"]


@pytest.mark.asyncio
async def test_a_quota_error_is_not_retried(monkeypatch):
    """Retrying everything would double every real outage — and spend twice
    the allowance of a provider that just said it has none left."""
    calls: list = []
    _wire(
        monkeypatch,
        calls,
        first_error=RuntimeError("groq 429: rate_limit_exceeded, retry in 60s"),
        then=_GOOD,
    )

    parsed, tried, _ = await runtime._generate_edits(
        "task", tenant_id="t", project_slug=None, user_subject=None
    )
    assert len(calls) == 1, "a rate limit was retried as if it were a format problem"
    assert parsed == {} and tried == []


@pytest.mark.asyncio
async def test_the_retry_happens_once(monkeypatch):
    calls: list = []

    async def _always_json_error(prompt, **kwargs):  # noqa: ANN001
        calls.append(kwargs.get("response_format"))
        raise RuntimeError("400 json_validate_failed")

    monkeypatch.setattr(
        "app.cascade.orchestrator.call_with_cascade", _always_json_error, raising=False
    )
    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers", lambda **_k: ["groq"]
    )

    parsed, tried, _ = await runtime._generate_edits(
        "task", tenant_id="t", project_slug=None, user_subject=None
    )
    assert len(calls) == 2, "a provider that fails twice has answered"
    assert parsed == {}


@pytest.mark.asyncio
async def test_a_first_attempt_that_works_is_not_repeated(monkeypatch):
    calls: list = []
    _wire(monkeypatch, calls, first_error=None, then=_GOOD)

    parsed, _tried, _ = await runtime._generate_edits(
        "task", tenant_id="t", project_slug=None, user_subject=None
    )
    assert len(calls) == 1
    assert parsed.get("edits")
