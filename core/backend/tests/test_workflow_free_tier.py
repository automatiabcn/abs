# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Workflows run on the free tier.

A workflow executes unattended — on a schedule, from a trigger, while nobody is
watching. A fallback into a paid provider would spend the customer's money with
no one present to approve it, so the LLM node is pinned to the free chain and
says so when a paid provider was asked for.
"""

from __future__ import annotations

import asyncio

import pytest

from app.workflow_v10 import runner


class _Resp:
    text = "done"
    provider = "groq"


def _run_node(node, monkeypatch, free_chain=("groq", "cerebras")):
    captured = {}

    async def _fake_cascade(prompt, **kwargs):
        captured.update(kwargs)
        captured["prompt"] = prompt
        return _Resp()

    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers",
        lambda **kw: list(free_chain) if kw.get("skip_paid") else ["groq", "anthropic"],
    )
    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _fake_cascade)
    out = asyncio.run(runner._run_node(node, "llm_call", {}, "acme"))
    return out, captured


def test_an_llm_node_runs_on_the_free_chain(monkeypatch):
    node = {"name": "summarise", "config": {"prompt_template": "hello"}}
    out, captured = _run_node(node, monkeypatch)
    assert out["tier"] == "free"
    assert captured["primary"] == "groq"
    assert "anthropic" not in captured["fallbacks"], "no paid fallback, ever"


def test_a_paid_provider_is_skipped_and_said_so(monkeypatch):
    """Silently swapping the provider would leave the author thinking their
    paid model ran."""
    node = {"name": "summarise", "config": {"prompt_template": "hi", "provider": "anthropic"}}
    out, captured = _run_node(node, monkeypatch)
    assert captured["primary"] == "groq"
    assert "anthropic" in out["note"]
    assert "free tier" in out["note"]


def test_no_free_provider_means_the_step_is_skipped_not_charged(monkeypatch):
    node = {"name": "summarise", "config": {"prompt_template": "hi"}}
    out, _ = _run_node(node, monkeypatch, free_chain=())
    assert out["skipped"] == "llm_call"
    assert "do not use paid providers" in out["note"]


@pytest.mark.parametrize("requested", ["groq", "cerebras"])
def test_a_free_provider_named_by_the_node_is_honoured(monkeypatch, requested):
    node = {"name": "n", "config": {"prompt_template": "hi", "provider": requested}}
    _out, captured = _run_node(node, monkeypatch)
    assert captured["primary"] == requested
