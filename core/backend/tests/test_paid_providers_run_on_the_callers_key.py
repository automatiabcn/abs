"""A paid provider runs on the key of the person asking.

Audit 2026-08-18: the operator's Anthropic/OpenRouter key in the server env
was 'configured', the deep-work ranking put it ahead of every free provider,
and any token — a member, a script calling ask_opus — spent it. OpenRouter
had no pricing row, so the spend was reported as free.
"""

from __future__ import annotations

import json

import pytest

from app.providers import paid_access as pa
from app.providers.cascade import PAID_PROVIDERS


@pytest.fixture(autouse=True)
def operator_and_keys(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "admin_email", "owner@example.com", raising=False)
    monkeypatch.setattr(settings, "paid_server_keys_shared", False, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-server-key-000000000", raising=False)
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-server-key-0000000000", raising=False)
    monkeypatch.delenv("ABS_PAID_SERVER_KEYS_SHARED", raising=False)


def test_a_member_may_not_spend_the_servers_paid_key():
    assert pa.allowed_paid(byok=(), user_subject="member@example.com") == frozenset()
    assert pa.refusal("anthropic", (), "member@example.com")
    assert pa.restrict_chain(["anthropic", "groq", "openrouter", "gemini"], (), "member@example.com") == ["groq", "gemini"]


def test_a_members_own_key_is_theirs():
    assert "anthropic" in pa.allowed_paid(byok=("anthropic",), user_subject="member@example.com")
    assert pa.refusal("anthropic", ("anthropic",), "member@example.com") is None
    # ...and only that one.
    assert "openrouter" not in pa.allowed_paid(byok=("anthropic",), user_subject="member@example.com")


def test_the_operator_may_use_the_keys_they_set():
    assert pa.allowed_paid(byok=(), user_subject="owner@example.com") == PAID_PROVIDERS
    assert pa.refusal("openrouter", (), "Owner@Example.com") is None  # case-insensitive


def test_the_operator_can_share_the_servers_keys(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "paid_server_keys_shared", True, raising=False)
    assert pa.allowed_paid(byok=(), user_subject="member@example.com") == PAID_PROVIDERS


def test_free_providers_are_never_touched():
    assert pa.restrict_chain(["groq", "cerebras", "gemini"], (), None) == ["groq", "cerebras", "gemini"]
    assert pa.refusal("groq", (), None) is None


def test_no_caller_identity_means_no_paid_server_key():
    assert pa.allowed_paid(byok=(), user_subject=None) == frozenset()


# --- doors -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_cascade_ask_refuses_prefer_on_a_paid_server_key(monkeypatch):
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import engine_panel_tools as ept

    monkeypatch.setattr(ept, "_caller_tenant", lambda: "default", raising=False)
    monkeypatch.setattr(ept, "_caller_user", lambda: "member@example.com", raising=False)
    monkeypatch.setattr(ept, "get_active_providers", lambda **k: ["anthropic", "groq"], raising=False)
    called = {}

    async def fake_cascade(prompt, **kwargs):
        called.update(kwargs)

        class R:
            text = "ok"; provider = "groq"; model = "m"; tokens_in = 1; tokens_out = 1; cached = False; truncated = False

        return R()

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", fake_cascade)
    out = json.loads(await ept.cascade_ask("hi", prefer="anthropic", use_cache=False))
    assert out["ok"] is False and "paid provider" in out["detail"], out
    assert not called
    out2 = json.loads(await ept.cascade_ask("hi", use_cache=False))
    assert out2["ok"] is True
    assert called["primary"] == "groq" and "anthropic" not in called["fallbacks"]


@pytest.mark.asyncio
async def test_ask_opus_refuses_without_the_callers_key(monkeypatch):
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import anthropic_tools as at

    monkeypatch.setattr(at, "_caller", lambda: ("default", "member@example.com"))
    monkeypatch.setattr(at, "call_with_cascade", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call")))
    out = await at.ask_opus("hi")
    assert out.startswith("[REFUSED]") and "add your own anthropic key" in out


@pytest.mark.asyncio
async def test_ask_opus_runs_for_the_operator(monkeypatch):
    import app.mcp.server  # noqa: F401
    from app.mcp.tools import anthropic_tools as at

    monkeypatch.setattr(at, "_caller", lambda: ("default", "owner@example.com"))

    async def fake(prompt, **kwargs):
        class R:
            text = "yes"

        return R()

    monkeypatch.setattr(at, "call_with_cascade", fake)
    assert await at.ask_opus("hi") == "yes"


def test_composer_chain_drops_the_servers_paid_key_for_a_member(monkeypatch):
    from app.composer import runtime

    seen = {}

    async def fake_cascade(prompt, **kwargs):
        seen.update(kwargs)

        class R:
            text = '{"summary":"s","edits":[]}'; provider = "groq"; model = "m"; tokens_in = 1; tokens_out = 1; cached = False; truncated = False

        return R()

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", fake_cascade)
    monkeypatch.setattr("app.providers.cascade.get_active_providers", lambda **k: ["anthropic", "groq", "openrouter"])
    import asyncio

    asyncio.run(runtime._generate_edits("t", tenant_id="default", project_slug=None, user_subject="member@example.com", files=[], contents=[]))
    assert seen["primary"] == "groq"
    assert "anthropic" not in seen["fallbacks"] and "openrouter" not in seen["fallbacks"]


def test_disagree_does_not_spend_the_servers_paid_key(monkeypatch):
    from app.disagreement import detector

    monkeypatch.setattr(detector, "byok_providers", lambda t, u: frozenset())
    monkeypatch.setattr(detector, "get_active_providers", lambda **k: ["anthropic", "groq", "cloudflare", "gemini"])
    chosen = [p for p, _n, _m in detector.choose_models("default", "member@example.com")]
    assert "anthropic" not in chosen and "groq" in chosen


# --- cost honesty ----------------------------------------------------------

def test_an_unpriced_paid_call_is_not_reported_as_free():
    from app.chat.cost import estimate_call_cost_usd

    out = estimate_call_cost_usd(provider="openrouter", tokens_in=100, tokens_out=100, model="some/new-model")
    assert out["usd"] is None and out["free"] is False and "unpriced" in out["source"]


def test_an_unknown_anthropic_model_is_not_priced_as_haiku():
    from app.chat.cost import estimate_call_cost_usd

    out = estimate_call_cost_usd(provider="anthropic", tokens_in=1000, tokens_out=1000, model="claude-something-new")
    assert out["usd"] is None and out["free"] is False


def test_a_free_tier_provider_without_a_row_stays_free():
    from app.chat.cost import estimate_call_cost_usd

    out = estimate_call_cost_usd(provider="mlx", tokens_in=10, tokens_out=10, model="x")
    assert out["free"] is True
