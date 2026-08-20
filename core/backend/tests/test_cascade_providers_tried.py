# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The failover trail is exposed on the success path, not only on total failure.

chat / the Cost HUD needs to show "tried cloudflare -> groq"; the orchestrator
computed that list but dropped it on success and only carried it in
CascadeUnavailable. Unique tenant_ids keep the global breaker out of the way.
"""

from __future__ import annotations

import pytest

from app.cascade import orchestrator
from app.providers.schemas import ProviderError, ProviderResponse


class _Dead:
    async def call(self, prompt, model=None, **kwargs):
        raise ProviderError("temporarily down", provider="cloudflare", transient=True)


class _Alive:
    async def call(self, prompt, model=None, **kwargs):
        return ProviderResponse(text="the answer", provider="groq", model="m", elapsed_ms=1)


@pytest.mark.asyncio
async def test_trail_includes_failed_then_winning_provider(monkeypatch):
    monkeypatch.setattr(
        orchestrator, "get_provider",
        lambda name: _Dead() if name == "cloudflare" else _Alive(),
    )
    resp = await orchestrator.call_with_cascade(
        "x", primary="cloudflare", fallbacks=("groq",),
        use_cache=False, tenant_id="t_ptried_1",
    )
    assert resp.text == "the answer"
    assert resp.providers_tried == ["cloudflare", "groq"]  # trail, winner last


@pytest.mark.asyncio
async def test_trail_is_single_when_primary_wins(monkeypatch):
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: _Alive())
    resp = await orchestrator.call_with_cascade(
        "x", primary="groq", use_cache=False, tenant_id="t_ptried_2",
    )
    assert resp.providers_tried == ["groq"]


@pytest.mark.asyncio
async def test_cache_hit_reports_empty_trail(monkeypatch):
    monkeypatch.setattr(orchestrator, "get_provider", lambda name: _Alive())
    # First call populates the cache for this tenant...
    first = await orchestrator.call_with_cascade(
        "same-prompt", primary="groq", use_cache=True, tenant_id="t_ptried_3",
    )
    assert first.providers_tried == ["groq"]
    # ...second call is a cache hit and tried nothing.
    second = await orchestrator.call_with_cascade(
        "same-prompt", primary="groq", use_cache=True, tenant_id="t_ptried_3",
    )
    assert second.cached is True
    assert second.providers_tried == []
