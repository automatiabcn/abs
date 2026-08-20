# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""A whole file does not fit in 1500 tokens.

The Composer used to ask models for a unified diff and got malformed ones, so
it was changed to ask for `new_content` — "the COMPLETE file exactly as it
should be afterwards". That fixed the apply rate. The token ceiling stayed
where the diff-sized answers had left it: 1500.

A 200-line Python file is already past that. So the model's answer was cut off
mid-JSON, `_parse` found no balanced object, and the run came back with zero
edits, an empty summary, and `degraded: true` — while the call had been made
and billed. Measured on 2026-08-02: eight tasks, eight providers answered,
eight empty proposals, $0.006 each.

Two things are pinned:

* the ceiling has room for a real file;
* an answer that arrives and cannot be parsed says so. Silence and "the model
  had nothing to suggest" are different facts, and the reader was being handed
  the second when the first was true.
"""

from __future__ import annotations

import pytest

from app.composer import runtime


def test_the_ceiling_has_room_for_a_whole_file():
    # A 200-line source file is ~2.5k tokens; asking for the file back means
    # the answer carries at least that, plus the JSON around it.
    assert runtime._MAX_OUTPUT_TOKENS >= 6000, (
        "the prompt asks for the COMPLETE file and the ceiling only fits a diff"
    )


def test_the_prompt_still_asks_for_the_whole_file():
    """If this ever goes back to asking for a diff, the ceiling can come down
    with it — but the two have to move together."""
    text = runtime._prompt("t", ["a.py"], [("a.py", "x = 1\n")])
    assert "new_content" in text
    assert "COMPLETE file" in text or "WHOLE file" in text


@pytest.mark.asyncio
async def test_an_answer_that_cannot_be_parsed_says_so(monkeypatch):
    """The reader was told the model had nothing to suggest, when in fact the
    answer arrived and was cut off."""

    class _Truncated:
        # Valid JSON right up to the point the ceiling stopped it.
        text = '{"summary": "ok", "edits": [{"path": "a.py", "new_content": "def f('
        provider = "cerebras"
        providers_tried = ["cerebras"]
        tokens_in = 900
        tokens_out = 1500
        model = "gpt-oss-120b"

    async def _fake(prompt, **_kwargs):  # noqa: ANN001
        return _Truncated()

    monkeypatch.setattr(
        "app.cascade.orchestrator.call_with_cascade", _fake, raising=False
    )
    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers", lambda **_k: ["cerebras"]
    )

    parsed, tried, meta = await runtime._generate_edits(
        "task", tenant_id="t", project_slug=None, user_subject=None
    )
    assert parsed == {}, "unparseable is unparseable"
    assert meta.get("parse_failed") is True, (
        "an answer that arrived and could not be read was reported the same "
        "way as no answer at all"
    )
    assert tried == ["cerebras"], "the provider that answered must still be named"


@pytest.mark.asyncio
async def test_a_readable_answer_is_not_flagged(monkeypatch):
    class _Fine:
        text = '{"summary": "ok", "edits": []}'
        provider = "cerebras"
        providers_tried = ["cerebras"]
        tokens_in = tokens_out = 10
        model = "gpt-oss-120b"

    async def _fake(prompt, **_kwargs):  # noqa: ANN001
        return _Fine()

    monkeypatch.setattr(
        "app.cascade.orchestrator.call_with_cascade", _fake, raising=False
    )
    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers", lambda **_k: ["cerebras"]
    )

    _parsed, _tried, meta = await runtime._generate_edits(
        "task", tenant_id="t", project_slug=None, user_subject=None
    )
    assert not meta.get("parse_failed")
