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
