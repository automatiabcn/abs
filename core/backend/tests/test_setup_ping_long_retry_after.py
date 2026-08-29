"""A Retry-After the wizard cannot afford to wait for still proves the key.

CI run 33200314981 (2026-08-28): Groq answered the wizard's ping with 429
and `Retry-After: 423` — the key's longer-window quota was spent. The
cascade's second pass waited its twenty-second cap, the wizard's timeout
fired first, and a proven key was reported as "nothing answered". The
wizard now paces its own retry, reads the hint, and when the hint is longer
than a wizard step should take it reports the key as accepted and says when
the provider will answer — without waiting.
"""

from __future__ import annotations

import pytest

from app.api import setup as setup_mod
from app.providers.schemas import CascadeUnavailable, ProviderError


@pytest.fixture()
def _groq_only(monkeypatch):
    monkeypatch.setattr(
        setup_mod, "read_state",
        lambda: {"data": {"providers_configured": ["groq_api_key"]}},
    )
    monkeypatch.delenv("ABS_TEST_MODE", raising=False)
    monkeypatch.setattr("app.providers.cascade.is_configured", lambda name: False)


async def test_long_retry_after_is_reported_without_waiting(_groq_only, monkeypatch):
    slept = []

    async def _sleep(s):
        slept.append(s)

    monkeypatch.setattr(setup_mod.asyncio, "sleep", _sleep)
    calls = {"n": 0}

    async def _cascade(prompt, **kw):
        calls["n"] += 1
        assert kw.get("_second_pass") is True, "the wizard must switch the cascade's own second pass off"
        raise CascadeUnavailable(
            "every provider in the chain failed; some may recover shortly",
            providers_tried=["groq"],
            last_error=ProviderError("groq rate limit (retry after 423s)", provider="groq", transient=True, retry_after=423.0),
        )

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _cascade)
    out = await setup_mod._run_provider_tests()
    r = out["groq_api_key"]
    assert r["status"] == "ok" and r["rate_limited"] is True
    assert r["retry_after"] == 423.0
    assert "about 7 min" in r["reason"]
    assert calls["n"] == 1, "no retry when the provider named a wait beyond the budget"
    assert slept == []


async def test_short_retry_after_is_waited_for_then_retried(_groq_only, monkeypatch):
    slept = []

    async def _sleep(s):
        slept.append(s)

    monkeypatch.setattr(setup_mod.asyncio, "sleep", _sleep)
    calls = {"n": 0}

    class _R:
        text = "pong"

    async def _cascade(prompt, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderError("groq rate limit (retry after 6s)", provider="groq", transient=True, retry_after=6.0)
        return _R()

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _cascade)
    out = await setup_mod._run_provider_tests()
    assert out["groq_api_key"]["status"] == "ok"
    assert "rate_limited" not in out["groq_api_key"]
    assert slept == [6.0]
    assert calls["n"] == 2
