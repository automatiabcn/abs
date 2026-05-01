"""Anthropic provider package — hexagonal layout (T-S02.1)."""

from .adapter import AnthropicProvider

__all__ = ["AnthropicProvider"]
API_VERSIONS = ("v1", "v2")
