"""'Ready' means the provider answered — not that a key exists.

Audit 2026-08-18: the title bar said '5 providers ready' while cerebras
answered 402 payment_required to every call and groq's default model had
been retired (404). The breaker opens after 5 failures in 60 s and closes a
minute later, so a permanently dead key flaps and reads healthy; the key was
probed once, when it was set. provider_health keeps the last outcome and
readiness readers ask it.
"""

from __future__ import annotations

import json

import pytest

from app.cascade import provider_health as ph


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    ph.reset_for_tests()
    monkeypatch.setattr(ph, "_path", lambda: str(tmp_path / "ph.json"))


def test_a_permanent_failure_makes_the_provider_degraded_until_it_answers():
    ph.note_failure("cerebras", tenant="t", permanent=True, detail="cerebras 402: payment required")
    assert "payment is required" in ph.degraded_reason("cerebras", "t")
    ph.note_success("cerebras", tenant="t")
    assert ph.degraded_reason("cerebras", "t") == ""


def test_a_transient_failure_is_not_a_verdict():
    ph.note_failure("groq", tenant="t", permanent=False, detail="groq timeout (30s)")
    assert ph.degraded_reason("groq", "t") == ""


def test_a_transient_failure_does_not_erase_a_standing_permanent_one():
    ph.note_failure("groq", tenant="t", permanent=True, detail="groq 401: invalid api key")
    ph.note_failure("groq", tenant="t", permanent=False, detail="groq rate limit")
    assert "rejects the key" in ph.degraded_reason("groq", "t")


@pytest.mark.parametrize(
    "detail,expect",
    [
        ("cerebras 402: {\"message\":\"Payment required\"}", "payment is required"),
        ("groq 404: model `llama-3.1-8b-instant` does not exist", "llama-3.1-8b-instant is not served"),
        ("cloudflare 401: Unauthorized", "rejects the key"),
        ("gemini 403: forbidden", "permissions"),
        ("something odd", "failed permanently"),
    ],
)
def test_the_reason_is_a_sentence_about_what_to_do(detail, expect):
    ph.note_failure("p", tenant="t", permanent=True, detail=detail)
    assert expect in ph.degraded_reason("p", "t")


def test_verdicts_survive_a_restart(monkeypatch, tmp_path):
    ph.note_failure("cerebras", tenant="t", permanent=True, detail="cerebras 402 payment")
    ph.reset_for_tests()
    assert "payment" in ph.degraded_reason("cerebras", "t")


def test_tenants_do_not_share_verdicts():
    ph.note_failure("groq", tenant="a", permanent=True, detail="groq 401")
    assert ph.degraded_reason("groq", "b") == ""


@pytest.mark.asyncio
async def test_the_cascade_records_what_each_provider_said(monkeypatch):
    from app.cascade import orchestrator as orch
    from app.providers.schemas import ProviderError, ProviderResponse

    class Dead:
        name = "cerebras"

        async def call(self, prompt, **kw):
            raise ProviderError("cerebras 402: payment required", provider="cerebras", transient=False)

    class Alive:
        name = "groq"

        async def call(self, prompt, **kw):
            return ProviderResponse(text="ok", provider="groq", model="m")

    monkeypatch.setattr(orch, "get_provider", lambda n: {"cerebras": Dead(), "groq": Alive()}[n])
    monkeypatch.setattr(orch, "_resolve_owner_key", lambda *a, **k: None)
    r = await orch.call_with_cascade("hi", primary="cerebras", fallbacks=("groq",), use_cache=False, tenant_id="t")
    assert r.provider == "groq"
    assert "payment" in ph.degraded_reason("cerebras", "t")
    assert ph.degraded_reason("groq", "t") == ""


@pytest.mark.asyncio
async def test_title_status_does_not_count_a_dead_provider_as_ready(monkeypatch):
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import engine_panel_tools as ept

    monkeypatch.setattr(ept, "_caller_tenant", lambda: "t", raising=False)
    monkeypatch.setattr(ept, "_caller_user", lambda: "u", raising=False)
    monkeypatch.setattr("app.providers.cascade.get_active_providers", lambda **k: ["cerebras", "groq"])
    monkeypatch.setattr("app.providers.cascade.is_configured", lambda p: True)
    ph.note_failure("cerebras", tenant="t", permanent=True, detail="cerebras 402 payment required")
    out = json.loads(await ept.title_status())
    assert out["providers"]["ready"] == 1, out
    assert out["providers"]["names"] == ["groq"]
    assert "payment" in out["providers"]["degraded"]["cerebras"]


def test_breakers_are_read_per_tenant(monkeypatch):
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import engine_panel_tools as ept

    raw = {"a|groq": {"state": "open"}, "b|groq": {"state": "closed"}, "cohere": {"state": "closed"}}
    assert ept._breakers_for(raw, "b")["groq"]["state"] == "closed"
    assert ept._breakers_for(raw, "a")["groq"]["state"] == "open"
    assert "cohere" in ept._breakers_for(raw, "b")
