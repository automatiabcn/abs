"""A 429 on the wizard's ping is not "nothing answered".

CI's scenarios were red from 2026-08-20: step 6 pinged Groq once, got a
per-minute rate limit, and the wizard said "No provider answered" — while
the same key answered 200 thirty seconds later in the same log. A provider
that says "slow down" has read the key and accepted it. The ping now retries
once after a short wait and, if still busy, reports the key as proven.
"""

from __future__ import annotations

import pytest

from app.api import setup as setup_mod
from app.providers.schemas import ProviderError


@pytest.fixture()
def _groq_only(monkeypatch):
    monkeypatch.setattr(
        setup_mod, "read_state",
        lambda: {"data": {"providers_configured": ["groq_api_key"]}},
    )
    monkeypatch.delenv("ABS_TEST_MODE", raising=False)
    monkeypatch.setattr(setup_mod, "_RATE_LIMIT_RETRY_S", 0.0)
    monkeypatch.setattr("app.providers.cascade.is_configured", lambda name: False)


class _R:
    text = "pong"


async def test_busy_then_answer_is_ok(_groq_only, monkeypatch):
    calls = {"n": 0}

    async def _cascade(prompt, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderError("groq rate limit", provider="groq", transient=True)
        return _R()

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _cascade)
    out = await setup_mod._run_provider_tests()
    assert out["groq_api_key"]["status"] == "ok"
    assert calls["n"] == 2
    assert "rate_limited" not in out["groq_api_key"]


async def test_still_busy_is_a_proven_key_not_a_failure(_groq_only, monkeypatch):
    async def _cascade(prompt, **kw):
        raise ProviderError("HTTP 429 Too Many Requests", provider="groq", transient=True)

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _cascade)
    out = await setup_mod._run_provider_tests()
    r = out["groq_api_key"]
    assert r["status"] == "ok"
    assert r["rate_limited"] is True
    assert "accepted the key" in r["reason"]


async def test_a_bad_key_is_still_a_failure(_groq_only, monkeypatch):
    async def _cascade(prompt, **kw):
        raise ProviderError("401 invalid api key", provider="groq", transient=False)

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _cascade)
    out = await setup_mod._run_provider_tests()
    assert out["groq_api_key"]["status"] == "fail"
    assert "401" in out["groq_api_key"]["reason"]


async def test_a_rate_limit_wrapped_by_the_cascade_is_still_recognised(_groq_only, monkeypatch):
    """CI, 2026-08-28: the chain's two 429s reached the wizard as
    CascadeUnavailable('every provider in the chain failed…') and were
    reported as 'nothing answered'. The reason is on last_error."""
    from app.providers.schemas import CascadeUnavailable

    async def _cascade(prompt, **kw):
        raise CascadeUnavailable(
            "every provider in the chain failed; some may recover shortly",
            providers_tried=["groq"],
            last_error=ProviderError("groq rate limit", provider="groq", transient=True),
        )

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _cascade)
    out = await setup_mod._run_provider_tests()
    assert out["groq_api_key"]["status"] == "ok"
    assert out["groq_api_key"]["rate_limited"] is True
