# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Per-tenant provider quota meter — record / throttle / status / isolation."""

from __future__ import annotations

import pytest

from app.cascade import quota_meter as qm


@pytest.fixture(autouse=True)
def _clean_meter():
    qm.reset()
    yield
    qm.reset()


def test_rpm_full_throttles_on_a_burst():
    # openrouter rpm=20: sending faster than that in one minute is throttled.
    for _ in range(qm.QUOTA_LIMITS["openrouter"]["rpm"]):
        qm.record_usage("openrouter", tenant_id="a", status_code=200)
    throttled, reason = qm.is_throttled("openrouter", tenant_id="a")
    assert throttled is True
    assert reason.startswith("rpm_full")


def test_rpd_exhaustion_throttles():
    limit = qm.QUOTA_LIMITS["openrouter"]["rpd"]
    for _ in range(limit):
        qm.record_usage("openrouter", tenant_id="a", status_code=200)
    # Isolate RPD from RPM: simulate the 60s minute-window clearing.
    qm._get("a", "openrouter")["minute_window"] = []
    throttled, reason = qm.is_throttled("openrouter", tenant_id="a")
    assert throttled is True
    assert reason.startswith("rpd_exhausted")


def test_429_sets_cooldown():
    qm.record_usage("groq", tenant_id="a", status_code=429)
    throttled, reason = qm.is_throttled("groq", tenant_id="a")
    assert throttled is True
    assert reason.startswith("cooldown_")


def test_success_resets_consecutive_429_counter():
    qm.record_usage("groq", tenant_id="a", status_code=429)
    # A later success clears the streak (cooldown may still be pending, but the
    # backoff no longer escalates).
    qm.record_usage("groq", tenant_id="a", status_code=200)
    # New 429 should start the backoff from step 1 again, not keep escalating.
    st = qm._get("a", "groq")
    assert st["consecutive_429"] == 0


def test_tenant_isolation():
    for _ in range(qm.QUOTA_LIMITS["openrouter"]["rpd"]):
        qm.record_usage("openrouter", tenant_id="a", status_code=200)
    assert qm.is_throttled("openrouter", tenant_id="a")[0] is True
    # A different tenant is untouched.
    assert qm.is_throttled("openrouter", tenant_id="b")[0] is False


def test_unknown_provider_never_throttled():
    throttled, reason = qm.is_throttled("some-byok-provider", tenant_id="a")
    assert throttled is False
    assert reason == "no_limits"
    # Recording for an unknown provider is a no-op, not an error.
    qm.record_usage("some-byok-provider", tenant_id="a", status_code=429)


def test_get_all_status_shape():
    qm.record_usage("groq", tenant_id="a", tokens=100, status_code=200)
    st = qm.get_all_status(tenant_id="a")
    assert st["tenant"] == "a"
    assert "groq" in st["providers"]
    g = st["providers"]["groq"]
    assert g["rpd_used"] >= 1
    assert "throttled" in g and "rpd_left" in g


def test_looks_like_rate_limit():
    assert qm.looks_like_rate_limit("HTTP 429 Too Many Requests")
    assert qm.looks_like_rate_limit("provider rate-limit hit")
    assert qm.looks_like_rate_limit("daily quota exceeded")
    assert not qm.looks_like_rate_limit("404 not found: bad account id")


@pytest.mark.asyncio
async def test_orchestrator_records_successful_call(monkeypatch):
    from app.cascade import orchestrator
    from app.providers.schemas import ProviderResponse

    class _Alive:
        async def call(self, prompt, model=None, **kwargs):
            return ProviderResponse(
                text="ok", provider="groq", model="m", elapsed_ms=1, tokens_out=5
            )

    monkeypatch.setattr(orchestrator, "get_provider", lambda name: _Alive())
    await orchestrator.call_with_cascade(
        "x", primary="groq", use_cache=False, tenant_id="tq"
    )
    rem = qm.get_remaining("groq", tenant_id="tq")
    assert rem["rpd_used"] >= 1
