"""Gemini provider package — hexagonal layout (T-S02.1)."""

from .adapter import GeminiProvider

__all__ = ["GeminiProvider"]
API_VERSIONS = ("v1", "v1beta")
