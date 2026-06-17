# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Roadmap (d) — setup wizard step 6 now PINGS each configured provider with the
just-entered key (was always 'skipped'), so the operator sees in-wizard whether
their keys work. Test-mode-gated + non-blocking."""

from __future__ import annotations

import pytest

from app.api import setup as setup_mod


@pytest.fixture()
def _state_with_providers(monkeypatch):
    monkeypatch.setattr(
        setup_mod, "read_state",
        lambda: {"data": {
            "providers_configured": ["groq_api_key", "cf_account_id"],
            "anthropic_configured": True,
        }},
    )
    # default test env sets ABS_TEST_MODE=1 → real pings are skipped; clear it so
    # the live-ping path runs (with a mocked cascade so no real network).
    monkeypatch.delenv("ABS_TEST_MODE", raising=False)


async def test_real_ping_marks_ok_and_skips_non_pingable(_state_with_providers, monkeypatch):
    async def _ok_cascade(prompt, **kw):
        class _R:
            text = "pong"
        return _R()

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _ok_cascade)
    out = await setup_mod._run_provider_tests()

    assert out["groq_api_key"]["status"] == "ok"
    assert out["anthropic_api_key"]["status"] == "ok"
    # cf_account_id is not an independently pingable key
    assert out["cf_account_id"]["status"] == "skipped"


async def test_failed_ping_is_fail_not_blocking(_state_with_providers, monkeypatch):
    async def _boom_cascade(prompt, **kw):
        raise RuntimeError("401 invalid key")

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _boom_cascade)
    out = await setup_mod._run_provider_tests()

    assert out["groq_api_key"]["status"] == "fail"
    assert "401" in out["groq_api_key"]["reason"]


async def test_test_mode_skips_live_ping(monkeypatch):
    monkeypatch.setattr(
        setup_mod, "read_state",
        lambda: {"data": {"providers_configured": ["groq_api_key"], "anthropic_configured": False}},
    )
    monkeypatch.setenv("ABS_TEST_MODE", "1")
    out = await setup_mod._run_provider_tests()
    assert out["groq_api_key"]["status"] == "skipped"
    assert "test mode" in out["groq_api_key"]["reason"]
