# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""The capability tool reads the real meter, not a hopeful assumption.

`capabilities.assess` knows what to do with a resting provider; this file
proves the tool actually asks. The wiring is the part that silently rots — a
correct translator fed nothing reports a healthy install forever, and the only
way to catch that is to make the meter say "throttled" and watch the answer
change.

The meter is patched rather than exercised: reaching a real rate limit would
mean spending the developer's own daily allowance to prove a message.
"""

from __future__ import annotations

import asyncio
import json

import app.mcp.server  # noqa: F401  (registers the tools)
from app.mcp.tools import capability_tools


def _status() -> dict:
    return json.loads(asyncio.run(capability_tools.capability_status()))


def test_a_throttled_provider_reaches_the_readout(monkeypatch):
    monkeypatch.setattr(
        capability_tools, "_configured_providers", lambda: {"groq", "cerebras"}
    )
    monkeypatch.setattr(capability_tools, "_resolved_embedding_backend", lambda: "ollama")

    from app.cascade import quota_meter

    monkeypatch.setattr(
        quota_meter,
        "QUOTA_LIMITS",
        {"groq": {"rpd": 1000}, "cerebras": {"rpd": 1000}},
        raising=False,
    )
    monkeypatch.setattr(
        quota_meter,
        "is_throttled",
        lambda name, **_: (True, "rpd_exhausted_1000") if name == "cerebras" else (False, "ok"),
    )

    out = _status()
    assert "cerebras" in out["resting"], "the tool never asked the meter"
    # And it says when, not what to buy — the founder's rule (08-02).
    assert "renews at midnight UTC" in out["resting"]["cerebras"]
    assert "buy" not in out["resting"]["cerebras"].lower()

    caps = {c["key"]: c for c in out["capabilities"]}
    # Two keys, one answering: the pair capabilities are honestly off …
    assert caps["failover"]["available"] is False
    # … and the reason is the rest, with no shopping list attached.
    assert "Not right now" in caps["failover"]["blocked_by"]
    assert caps["failover"]["unlock_with"] == []
    # … while the single-provider ones keep working.
    assert caps["ask"]["available"] is True


def test_an_open_breaker_reaches_the_readout(monkeypatch):
    monkeypatch.setattr(
        capability_tools, "_configured_providers", lambda: {"groq", "cerebras"}
    )
    monkeypatch.setattr(capability_tools, "_resolved_embedding_backend", lambda: "ollama")

    from app.cascade.breaker import default_breaker

    # Breaker keys are tenant-namespaced once a call has been made; the tool
    # has to strip that or it would never match a provider name — and only
    # THIS caller's tenant counts (another tenant's open breaker is not our
    # outage, 2026-08-18), so the key carries the caller's tenant here.
    monkeypatch.setattr(
        default_breaker,
        "snapshot",
        lambda: {"default|cerebras": {"state": "open"}, "groq": {"state": "closed"}},
    )

    out = _status()
    assert "cerebras" in out["resting"], "namespaced breaker keys were not unwrapped"
    assert "retries by itself" in out["resting"]["cerebras"]
    assert "groq" not in out["resting"], "a closed breaker is not a resting provider"


def test_a_meter_that_cannot_be_read_does_not_invent_rest(monkeypatch):
    """An unreadable meter is unknown, not throttled. Guessing 'resting' would
    switch capabilities off on a healthy install."""
    monkeypatch.setattr(capability_tools, "_configured_providers", lambda: {"groq"})
    monkeypatch.setattr(capability_tools, "_resolved_embedding_backend", lambda: "ollama")

    from app.cascade import quota_meter

    def _boom(*_a, **_k):
        raise RuntimeError("meter unavailable")

    monkeypatch.setattr(quota_meter, "is_throttled", _boom)

    out = _status()
    assert out["resting"] == {}
    assert {c["key"] for c in out["capabilities"] if c["available"]} >= {"ask", "edit"}
