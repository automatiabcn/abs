# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""BYOK is not a cascade feature — it is a product promise.

The panel says "the providers you supplied a key for come first". Two ways
that promise breaks, both found by auditing our own fixes (07-31 / 08-01):

* a path builds its chain WITHOUT the caller's keys, so an install whose
  providers are all BYOK reports that it has none; and
* a path promotes the provider but calls the adapter directly, so the
  caller's KEY never travels and the adapter reads the operator's env.

These tests pin the contract of the shared helper and the one non-obvious
consumer (Tab), so a future path can be checked against something.
"""

from __future__ import annotations

import asyncio

from app.providers import byok


def test_an_unknown_caller_is_an_empty_set_not_an_error():
    assert byok.byok_providers(None) == frozenset()
    assert byok.byok_providers("") == frozenset()
    assert byok.owner_key_for("groq", tenant_slug=None) is None


def test_a_broken_lookup_never_takes_the_call_down(monkeypatch):
    """BYOK is a bonus. A DB hiccup must degrade to the operator's keys, not
    raise into a user's request."""

    def _boom(**_kw):
        raise RuntimeError("db is having a moment")

    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers", _boom
    )
    monkeypatch.setattr("app.multitenant.provider_keys.resolve_provider_key", _boom)
    assert byok.byok_providers("acme", "alice@acme") == frozenset()
    assert byok.owner_key_for("groq", tenant_slug="acme", user_subject="alice") is None


def test_the_helper_returns_what_the_cascade_expects(monkeypatch):
    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers",
        lambda **_kw: {"cerebras", "cohere"},
    )
    out = byok.byok_providers("acme", "alice@acme")
    assert out == frozenset({"cerebras", "cohere"})
    assert isinstance(out, frozenset), "get_active_providers takes a frozenset"


def test_tab_sends_the_callers_own_key_not_just_their_order(monkeypatch):
    """The promotion was real and the credential did not follow: cerebras went
    first and the adapter answered 'api key is not configured' (08-01). What
    proves the fix is the api_key that reaches the adapter."""
    from app.fim import complete as fim

    monkeypatch.setattr(fim, "_free_fast_chain", lambda *a, **k: ["cerebras"])
    monkeypatch.setattr(
        "app.multitenant.provider_keys.resolve_provider_key",
        lambda provider, **_kw: "csk-the-users-own" if provider == "cerebras" else None,
    )
    seen: dict = {}

    class _P:
        async def call(self, prompt, **kw):
            seen.update(kw)
            return type("R", (), {"text": "a + b", "model": "gemma-4-31b"})()

    monkeypatch.setattr("app.providers.registry.get_provider", lambda _n: _P())
    out = asyncio.run(
        fim.complete(
            "def add(a, b):\n    return ",
            "\n",
            tenant_id="acme",
            user_subject="alice@acme",
        )
    )
    assert out["provider"] == "cerebras"
    assert seen.get("api_key") == "csk-the-users-own", "the key must travel"


def test_tab_without_a_caller_uses_the_operators_keys(monkeypatch):
    """No caller identity means no BYOK — and no api_key override either, so
    the adapter stays on the operator's environment."""
    from app.fim import complete as fim

    monkeypatch.setattr(fim, "_free_fast_chain", lambda *a, **k: ["groq"])
    seen: dict = {}

    class _P:
        async def call(self, prompt, **kw):
            seen.update(kw)
            return type("R", (), {"text": "a + b", "model": "m"})()

    monkeypatch.setattr("app.providers.registry.get_provider", lambda _n: _P())
    asyncio.run(fim.complete("x = ", ""))
    assert "api_key" not in seen


def test_the_judge_survives_a_dead_first_provider_without_changing_model(monkeypatch):
    """Scores are only comparable if the same model produced them, so the
    judge's fallback changes WHO serves gpt-oss-120b, never which model runs.
    Pinned live (08-01): cerebras answers the judge prompt in the same shape."""
    from app.judge import senior

    models_used: list = []

    class _Dead:
        async def call(self, prompt, **kw):
            models_used.append(("groq", kw.get("model")))
            raise RuntimeError("quota exhausted")

    class _Alive:
        async def call(self, prompt, **kw):
            models_used.append(("cerebras", kw.get("model")))
            return type("R", (), {"text": '{"score": 7.5, "teaching": "fine"}'})()

    monkeypatch.setattr(senior, "_server_has_key", lambda _p: True)
    # senior.py binds get_provider at import time — patching the registry
    # module would leave its own reference untouched.
    monkeypatch.setattr(
        senior, "get_provider", lambda name: _Dead() if name == "groq" else _Alive()
    )
    out = asyncio.run(senior._llm_judge("x = 1", diff_text="@@\n+x = 1\n"))
    assert out["score"] == 7.5
    assert [m for _p, m in models_used] == ["openai/gpt-oss-120b", "gpt-oss-120b"], (
        "one model, two spellings — never a different judge"
    )


def test_a_byok_only_install_still_has_a_judge(monkeypatch):
    """No server key anywhere; the caller brought cerebras. Before this, every
    file came back 'not graded' on an install that could clearly grade."""
    from app.judge import senior

    seen: dict = {}

    class _P:
        async def call(self, prompt, **kw):
            seen.update(kw)
            return type("R", (), {"text": '{"score": 6, "teaching": "ok"}'})()

    monkeypatch.setattr(senior, "_server_has_key", lambda _p: False)
    monkeypatch.setattr(
        "app.multitenant.provider_keys.resolve_provider_key",
        lambda provider, **_kw: "csk-mine" if provider == "cerebras" else None,
    )
    monkeypatch.setattr(senior, "get_provider", lambda _n: _P())
    out = asyncio.run(
        senior._llm_judge(
            "x = 1", diff_text="@@\n+x = 1\n",
            tenant_id="acme", user_subject="alice@acme",
        )
    )
    assert out["score"] == 6.0
    assert seen.get("api_key") == "csk-mine"
    assert seen.get("model") == "gpt-oss-120b"


def test_no_key_anywhere_is_unjudged_not_zero(monkeypatch):
    """An install with no judge provider must report UNKNOWN — a 0 here would
    read as 'worst possible code' in the review panel."""
    from app.judge import senior

    monkeypatch.setattr(senior, "_server_has_key", lambda _p: False)
    monkeypatch.setattr(
        "app.multitenant.provider_keys.resolve_provider_key", lambda *a, **k: None
    )
    out = asyncio.run(senior._llm_judge("x = 1", diff_text="@@\n+x = 1\n"))
    assert out["score"] is None
    assert "unavailable" in out["teaching"].lower()
