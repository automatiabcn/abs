"""Cohere provider package — hexagonal layout (T-S02.1)."""

from .adapter import CohereProvider

__all__ = ["CohereProvider"]
API_VERSIONS = ("v1", "v2")
