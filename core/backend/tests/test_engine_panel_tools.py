# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.

"""Engine-panel MCP tools — the editor's side panels only reach /mcp.

These three exist because the data was already computed and had no door: the
quota meter's counters, the cascade's provenance, and a pipeline's steps.
"""

from __future__ import annotations

import asyncio
import json

import pytest

# The MCP server is the entry point that registers every tool module; importing
# a tool module first would re-enter it mid-initialisation.
from app.mcp.server import mcp_server  # noqa: F401  (import order matters)

from app.cascade import quota_meter
from app.mcp.tools import engine_panel_tools as ep


def _call(coro):
    return json.loads(asyncio.run(coro))


def test_quota_meter_status_reports_real_counters(monkeypatch):
    quota_meter.reset()
    monkeypatch.setattr(ep, "_caller_tenant", lambda: "t-panel")
    for _ in range(3):
        quota_meter.record_usage("groq", tenant_id="t-panel", tokens=100)

    out = _call(ep.quota_meter_status())
    groq = out["providers"]["groq"]
    assert groq["rpd_used"] == 3
    assert groq["rpd_left"] == quota_meter.QUOTA_LIMITS["groq"]["rpd"] - 3
    assert groq["throttled"] is False
    assert "configured" in groq, "a gauge must say whether the key even exists"
    assert out["limits"]["groq"]["rpd"] > 0
    # The panel must not present these as the provider's own numbers.
    assert "not fetched from the provider" in out["note"]


def test_quota_meter_status_is_tenant_scoped(monkeypatch):
    quota_meter.reset()
    monkeypatch.setattr(ep, "_caller_tenant", lambda: "tenant-a")
    quota_meter.record_usage("groq", tenant_id="tenant-a", tokens=10)
    assert _call(ep.quota_meter_status())["providers"]["groq"]["rpd_used"] == 1

    monkeypatch.setattr(ep, "_caller_tenant", lambda: "tenant-b")
    assert _call(ep.quota_meter_status())["providers"]["groq"]["rpd_used"] == 0


def test_cascade_ask_returns_provenance_not_just_text(monkeypatch):
    """The whole point: ask_* drops which provider answered, so the editor
    could never show the failover story that makes an answer trustworthy."""

    class _Resp:
        text = "hello"
        provider = "cerebras"
        model = "gpt-oss-120b"
        providers_tried = ["groq", "cerebras"]
        cached = False
        tokens_in = 10
        tokens_out = 5

    async def _fake_cascade(prompt, **kwargs):
        return _Resp()

    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers", lambda **_: ["groq", "cerebras"]
    )
    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _fake_cascade)

    out = _call(ep.cascade_ask("hi"))
    assert out["ok"] is True
    assert out["text"] == "hello"
    assert out["provider"] == "cerebras"
    assert out["providers_tried"] == ["groq", "cerebras"]
    assert out["tokens_in"] == 10 and out["tokens_out"] == 5
    assert "cost_usd" in out and "elapsed_ms" in out


def test_cascade_ask_says_so_when_no_provider_is_configured(monkeypatch):
    monkeypatch.setattr("app.providers.cascade.get_active_providers", lambda **_: [])
    out = _call(ep.cascade_ask("hi"))
    assert out["ok"] is False
    assert out["error"] == "no_provider_configured"


def test_pipeline_run_returns_structured_steps(monkeypatch):
    """The existing pipeline tools flatten the chain into a summary line; a
    panel needs the steps as data to draw the delegation chain."""

    class _Step:
        def __init__(self, name, model):
            self.name = name
            self.model = model
            self.elapsed_ms = 120
            self.ok = True
            self.error = None
            self.meta = {"tokens_in": 7, "tokens_out": 9}

    class _Result:
        pipeline_type = "qual_code"
        steps = [_Step("generate", "kimi"), _Step("verify", "codellama")]
        final_response = "done"
        total_elapsed_ms = 240
        error = None
        workflow_trace_id = "trace-1"

    class _Fake:
        async def run(self, prompt):
            return _Result()

    monkeypatch.setattr(ep, "_pipeline_classes", lambda: {"qual_code": _Fake})

    out = _call(ep.pipeline_run("write a function", kind="qual_code"))
    assert out["ok"] is True
    assert [s["name"] for s in out["steps"]] == ["generate", "verify"]
    assert [s["model"] for s in out["steps"]] == ["kimi", "codellama"]
    assert out["steps"][0]["tokens_in"] == 7
    assert out["total_elapsed_ms"] == 240
    assert out["trace_id"] == "trace-1"


def test_pipeline_run_rejects_an_unknown_kind():
    out = _call(ep.pipeline_run("x", kind="not-a-pipeline"))
    assert out["ok"] is False
    assert out["error"] == "unknown_pipeline"
    assert "qual_code" in out["known"]


@pytest.mark.parametrize(
    "name", ["quota_meter_status", "cascade_ask", "pipeline_run"]
)
def test_tools_are_registered(name):
    from app.mcp.server import mcp_server

    names = {t.name for t in asyncio.run(mcp_server.list_tools())}
    assert name in names
