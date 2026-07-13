# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""What a provider gives back, in one shape whoever answered."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ProviderResponse(BaseModel):
    """One provider's answer, normalised."""

    text: str = Field(default="", description="The answer itself")
    model: str = Field(default="", description="Which model answered")
    provider: str = Field(default="", description="Which provider answered (groq, gemini, …)")
    elapsed_ms: int = Field(default=0, description="How long it took, in milliseconds")
    tokens_in: Optional[int] = Field(default=None, description="Tokens in the question")
    tokens_out: Optional[int] = Field(default=None, description="Tokens in the answer")
    cached: bool = Field(default=False, description="True if this came from the cache, not the provider")
    error: Optional[str] = Field(default=None, description="Why it failed, if it did")


class ProviderError(Exception):
    """A provider call failed. The cascade catches this and tries the next one."""

    def __init__(self, message: str, provider: str = "", transient: bool = True):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.transient = transient


class CascadeUnavailable(ProviderError):
    """Every provider in the chain failed, and at least one might recover.

    This is a ProviderError on purpose. The cascade used to raise a FastAPI
    ``HTTPException`` here — a web-framework exception thrown from a library
    that agents, MCP tools, pipelines and background workers all call. None of
    them are behind a web request, and every one of them was catching
    ``ProviderError`` and nothing else, so this sailed straight through their
    error handling: an agent mid-stream died on a rate limit, and a provider
    test whose provider was merely busy came back as a raw 503 instead of "busy,
    try again".

    Being a ProviderError means everything that already knows how to degrade
    gracefully now degrades gracefully. The HTTP layer keeps its 503 — an
    exception handler translates this into exactly the response it used to
    build, headers and all.
    """

    def __init__(
        self,
        message: str,
        *,
        providers_tried: list[str] | None = None,
        last_error: Exception | None = None,
        retry_after: int = 60,
    ):
        super().__init__(message, provider="", transient=True)
        self.providers_tried = providers_tried or []
        self.last_error = last_error
        self.retry_after = retry_after

    def detail(self) -> dict:
        """The body the HTTP layer returns — unchanged from the old 503."""
        out: dict = {
            "error": "providers_unavailable",
            "providers_tried": list(self.providers_tried),
            "retry_after": self.retry_after,
        }
        if self.last_error is not None:
            out["last_error_class"] = type(self.last_error).__name__
            # The class name alone ("ProviderError") tells an operator nothing
            # about which half of their configuration is wrong. The message does.
            out["last_error"] = str(self.last_error)[:300]
        return out
