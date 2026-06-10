# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""Regression — chat content at the 8000-char limit + RAG-grounding augmentation
must not 500.

The chat path builds the cascade prompt as ``grounding_preamble + retrieved
context + user_content``. ``ChatMessageIn.content`` and ``CascadeRequest.prompt``
share an 8000-char ceiling, so a max-length user message plus injected RAG
context overflows ``CascadeRequest.prompt`` → an unhandled pydantic
``ValidationError`` → HTTP 500. (Surfaced as an order-dependent flake in the full
suite: it only fires once a prior test has ingested RAG documents, so the chat's
auto-RAG actually injects context.) ``_run_cascade`` now clamps the validation /
mock copy of the request; the real orchestrator call still receives the full
augmented prompt.
"""
from __future__ import annotations

import pytest

from app.api.chat import _run_cascade
from app.config import settings


@pytest.fixture()
def _mock_mode(monkeypatch):
    monkeypatch.setenv("ABS_ANTHROPIC_MOCK_MODE", "ok")
    monkeypatch.setattr(settings, "anthropic_mock_mode", "ok", raising=False)


async def test_run_cascade_clamps_rag_augmented_oversized_prompt(_mock_mode):
    """An augmented prompt longer than CascadeRequest's 8000-char user cap (a
    max-length message + RAG context) must not raise ValidationError."""
    augmented = (
        "You are answering using the sources below. Cite inline.\n\n"
        + "a" * 9000
    )
    assert len(augmented) > 8000
    # The key assertion is that this call RETURNS (no ValidationError raised on
    # CascadeRequest's 8000-char prompt cap); the mock provider echoes the prompt.
    resp = await _run_cascade(augmented, max_tokens=64)
    assert resp is not None
    assert resp.completion  # non-empty mock completion proves the call ran
