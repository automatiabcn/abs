"""Cohere v1 surface — chat, embed, rerank pre-V2."""

from __future__ import annotations

API_VERSION: str = "v1"
SUPPORTED_MODELS: tuple[str, ...] = (
    "command-r",
    "command-r-plus",
    "embed-english-v3.0",
    "rerank-multilingual-v3.0",
)
