# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""BYOK — a customer's own Anthropic key must actually answer them.

It did not. The cascade sorted the caller's own provider to the front of the
chain (`get_active_providers`, which is what the old test checked), the adapter
then refused the call because the *operator* had not set ABS_ANTHROPIC_ENABLED,
and the cascade moved on and answered from the free tier. The customer paid
Anthropic for a model they never reached, and nothing anywhere said so.

The old test asserted `chain[0] == "anthropic"` — the order of a list. It never
drove a call, so the refusal two layers down was invisible to it. These tests
drive the call.
"""

from __future__ import annotations

import sys
import types

import pytest

from app.config import settings
from app.providers.anthropic.adapter import AnthropicProvider
from app.providers.schemas import ProviderError


class _FakeMessages:
    def __init__(self, client):
        self._client = client

    async def create(self, **kw):
        _FakeAnthropic.calls.append({"api_key": self._client.api_key, **kw})
        block = types.SimpleNamespace(text="hello from claude")
        usage = types.SimpleNamespace(input_tokens=10, output_tokens=5)
        return types.SimpleNamespace(content=[block], usage=usage)


class _FakeAnthropic:
    calls: list = []

    def __init__(self, api_key=None, **kw):
        self.api_key = api_key
        self.messages = _FakeMessages(self)


@pytest.fixture
def anthropic_sdk(monkeypatch):
    """Stand in for the `anthropic` package — the adapter imports it lazily."""
    _FakeAnthropic.calls = []
    monkeypatch.setitem(
        sys.modules, "anthropic", types.SimpleNamespace(AsyncAnthropic=_FakeAnthropic)
    )
    return _FakeAnthropic


@pytest.fixture
def free_tier_operator(monkeypatch):
    """The default install: the operator never turned the paid provider on."""
    monkeypatch.setattr(settings, "anthropic_enabled", False, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "", raising=False)


async def test_a_customers_own_key_reaches_anthropic_on_a_free_tier_server(
    anthropic_sdk, free_tier_operator
):
    """The bug, in one test. This raised ProviderError before."""
    resp = await AnthropicProvider().call("hi", api_key="sk-ant-customer-key")

    assert resp.text == "hello from claude"
    assert len(anthropic_sdk.calls) == 1
    # Their key, not the operator's.
    assert anthropic_sdk.calls[0]["api_key"] == "sk-ant-customer-key"


async def test_without_a_key_the_paid_provider_is_still_opt_in(
    anthropic_sdk, free_tier_operator
):
    """The flag's real job survives: no key of your own, and the operator has not
    opted in → this server does not spend the operator's money."""
    with pytest.raises(ProviderError) as exc:
        await AnthropicProvider().call("hi")

    assert "opt-in" in str(exc.value)
    assert anthropic_sdk.calls == []


async def test_the_operators_monthly_budget_does_not_gate_someone_elses_key(
    anthropic_sdk, free_tier_operator, monkeypatch
):
    """The quota gate protects the operator's Claude bill. A caller paying with
    their own key is not spending it — and being blocked by a budget that is not
    yours, on a key that is, is the same bug wearing a different hat."""
    from app.observability import quota_monitor as qm

    def _exhausted(**kw):
        raise qm.QuotaExceeded("monthly limit reached")

    monkeypatch.setattr(qm, "gate", _exhausted)

    resp = await AnthropicProvider().call("hi", api_key="sk-ant-customer-key")
    assert resp.text == "hello from claude"


async def test_the_operators_own_key_is_still_gated_by_the_operators_budget(
    anthropic_sdk, monkeypatch
):
    from app.observability import quota_monitor as qm

    monkeypatch.setattr(settings, "anthropic_enabled", True, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-operator", raising=False)

    def _exhausted(**kw):
        raise qm.QuotaExceeded("monthly limit reached")

    monkeypatch.setattr(qm, "gate", _exhausted)

    with pytest.raises(ProviderError) as exc:
        await AnthropicProvider().call("hi")

    assert "quota" in str(exc.value).lower()
    assert anthropic_sdk.calls == []


async def test_byok_spend_is_not_charged_to_the_operators_budget(
    anthropic_sdk, free_tier_operator, monkeypatch
):
    """Recording someone else's tokens against the operator's monthly budget eats
    a budget nobody spent, and eventually blocks the operator's own traffic."""
    from app.observability import quota_monitor as qm

    recorded: list = []
    monkeypatch.setattr(qm, "record", lambda **kw: recorded.append(kw))

    await AnthropicProvider().call("hi", api_key="sk-ant-customer-key")
    assert recorded == []

    monkeypatch.setattr(settings, "anthropic_enabled", True, raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-operator", raising=False)
    await AnthropicProvider().call("hi")
    assert len(recorded) == 1  # the operator's own call still counts
