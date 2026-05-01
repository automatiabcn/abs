"""Groq provider package — hexagonal layout (T-S02.1)."""

from .adapter import GroqProvider

__all__ = ["GroqProvider"]
API_VERSIONS = ("v1", "v2")
