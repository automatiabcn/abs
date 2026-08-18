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


# --- BYOK provider keys -----------------------------------------------------


def test_provider_key_set_is_scoped_to_the_calling_user(monkeypatch):
    """A delegated editor token must not be able to rewrite the organisation's
    credentials: a key set from the editor belongs to that user alone."""
    seen = {}

    def _fake_set(*, tenant_slug, owner_type, owner_id, provider, value):
        seen.update(
            tenant=tenant_slug, owner_type=owner_type, owner=owner_id,
            provider=provider, value=value,
        )
        return object()

    monkeypatch.setattr("app.multitenant.provider_keys.set_provider_key", _fake_set)
    monkeypatch.setattr(ep, "_caller_tenant", lambda: "acme")
    monkeypatch.setattr(ep, "_caller_user", lambda: "alice@acme")
    from app.providers.key_probe import KeyProbeResult

    monkeypatch.setattr(
        "app.providers.key_probe.probe_provider_key",
        lambda p, v: KeyProbeResult("valid"),
    )

    out = _call(ep.provider_key_set("cohere", "sk-secret"))
    assert out["ok"] is True
    assert seen["owner_type"] == "user", "an editor token must not set an org key"
    assert seen["owner"] == "alice@acme"
    assert seen["tenant"] == "acme"
    # The value must never come back out.
    assert "sk-secret" not in json.dumps(out)


def test_provider_key_set_refuses_without_a_user_identity(monkeypatch):
    monkeypatch.setattr(ep, "_caller_user", lambda: None)
    out = _call(ep.provider_key_set("cohere", "sk-secret"))
    assert out["ok"] is False
    assert out["error"] == "no_user_identity"


def test_provider_key_set_refuses_an_empty_value(monkeypatch):
    monkeypatch.setattr(ep, "_caller_user", lambda: "alice@acme")
    out = _call(ep.provider_key_set("cohere", "   "))
    assert out["ok"] is False
    assert out["error"] == "empty_value"


def test_a_key_the_provider_rejects_is_never_stored(monkeypatch):
    """Live incident (07-31): a key mangled in the input box sat in the chain
    as green 'ready' — readiness is breaker state and a never-called breaker
    is closed. The provider is asked FIRST; a rejected key does not get in."""
    from app.providers.key_probe import KeyProbeResult

    stored = []
    monkeypatch.setattr(
        "app.multitenant.provider_keys.set_provider_key",
        lambda **kw: stored.append(kw),
    )
    monkeypatch.setattr(ep, "_caller_tenant", lambda: "acme")
    monkeypatch.setattr(ep, "_caller_user", lambda: "alice@acme")
    monkeypatch.setattr(
        "app.providers.key_probe.probe_provider_key",
        lambda p, v: KeyProbeResult("rejected", "cohere rejected the key (401)"),
    )

    out = _call(ep.provider_key_set("cohere", "sk-mangled"))
    assert out["ok"] is False
    assert out["error"] == "key_rejected"
    assert "NOT stored" in out["detail"]
    assert stored == [], "a rejected key must never reach the vault"


def test_an_unreachable_provider_stores_the_key_but_says_unverified(monkeypatch):
    """A network fault is not a verdict on the key — but a key nobody has seen
    work must not read the same as one the provider just accepted."""
    from app.providers.key_probe import KeyProbeResult

    monkeypatch.setattr(
        "app.multitenant.provider_keys.set_provider_key",
        lambda **kw: object(),
    )
    monkeypatch.setattr(ep, "_caller_tenant", lambda: "acme")
    monkeypatch.setattr(ep, "_caller_user", lambda: "alice@acme")
    monkeypatch.setattr(
        "app.providers.key_probe.probe_provider_key",
        lambda p, v: KeyProbeResult("unreachable", "cohere could not be reached"),
    )

    out = _call(ep.provider_key_set("cohere", "sk-maybe"))
    assert out["ok"] is True
    assert out["verified"] is False
    assert "could not be reached" in out["note"]


def test_a_probe_accepted_key_reports_verified(monkeypatch):
    from app.providers.key_probe import KeyProbeResult

    monkeypatch.setattr(
        "app.multitenant.provider_keys.set_provider_key",
        lambda **kw: object(),
    )
    monkeypatch.setattr(ep, "_caller_tenant", lambda: "acme")
    monkeypatch.setattr(ep, "_caller_user", lambda: "alice@acme")
    monkeypatch.setattr(
        "app.providers.key_probe.probe_provider_key",
        lambda p, v: KeyProbeResult("valid"),
    )

    out = _call(ep.provider_key_set("gemini", "AIza-good"))
    assert out["ok"] is True
    assert out["verified"] is True


def test_provider_keys_list_returns_metadata_without_plaintext(monkeypatch):
    monkeypatch.setattr(ep, "_caller_tenant", lambda: "acme")
    monkeypatch.setattr(
        "app.multitenant.provider_keys.list_provider_keys",
        lambda *, tenant_slug: [
            {"provider": "cohere", "owner_type": "user", "owner_id": "alice@acme",
             "last_validated_ok": True}
        ],
    )
    out = _call(ep.provider_keys_list())
    assert out["ok"] is True
    assert out["keys"][0]["provider"] == "cohere"
    assert "value" not in out["keys"][0]


@pytest.mark.parametrize(
    "name", ["provider_keys_list", "provider_key_set", "provider_key_delete"]
)
def test_byok_tools_are_registered(name):
    from app.mcp.server import mcp_server as srv

    names = {t.name for t in asyncio.run(srv.list_tools())}
    assert name in names


def test_a_byok_key_makes_the_provider_count_as_configured(monkeypatch):
    """Live check found this: the panel told a user to add a key, they added it,
    and the gauge still said 'no key' — because only the SERVER's env was read.
    A key the account supplied is a key."""
    monkeypatch.setattr(ep, "_caller_tenant", lambda: "acme")
    monkeypatch.setattr(ep, "_caller_user", lambda: "alice@acme")
    monkeypatch.setattr(ep.settings, "cohere_api_key", "", raising=False)
    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers",
        lambda **_: {"cohere"},
    )
    out = _call(ep.quota_meter_status())
    cohere = out["providers"]["cohere"]
    assert cohere["configured"] is True
    assert cohere["key_source"] == "account", "whose key it is must be visible"


def test_a_server_key_is_labelled_as_the_servers(monkeypatch):
    monkeypatch.setattr(ep, "_caller_tenant", lambda: "acme")
    monkeypatch.setattr(ep.settings, "groq_api_key", "sk-server", raising=False)
    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers", lambda **_: set()
    )
    out = _call(ep.quota_meter_status())
    assert out["providers"]["groq"]["key_source"] == "server"


def test_a_broken_byok_lookup_does_not_break_the_gauge(monkeypatch):
    def _boom(**_):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers", _boom
    )
    out = _call(ep.quota_meter_status())
    assert "providers" in out, "the quota gauge must survive a BYOK lookup failure"


# --- the delegation chain ----------------------------------------------------


def test_the_chain_says_who_is_next_and_whose_key_answers(monkeypatch):
    monkeypatch.setattr(ep, "_caller_tenant", lambda: "acme")
    monkeypatch.setattr(ep, "_caller_user", lambda: "alice@acme")
    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers",
        lambda **_: {"cohere"},
    )
    monkeypatch.setattr(
        "app.providers.cascade.get_active_providers",
        lambda **_: ["cohere", "groq", "anthropic"],
    )
    monkeypatch.setattr("app.providers.cascade.is_configured", lambda p: p == "groq")

    out = _call(ep.providers_chain())
    assert out["ok"] is True
    chain = out["chain"]
    assert [s["provider"] for s in chain] == ["cohere", "groq", "anthropic"]
    assert [s["position"] for s in chain] == [1, 2, 3]
    # The account's own key comes first and is labelled as theirs.
    assert chain[0]["key_source"] == "account"
    assert chain[1]["key_source"] == "server"
    # Paid providers are named as paid — that is a bill, not a detail.
    assert chain[2]["paid"] is True
    assert chain[0]["paid"] is False


def test_the_workflow_chain_has_no_paid_provider_in_it(monkeypatch):
    seen = {}

    def _chain(**kw):
        seen.update(kw)
        return ["groq", "cerebras"]

    monkeypatch.setattr("app.providers.cascade.get_active_providers", _chain)
    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers", lambda **_: set()
    )
    out = _call(ep.providers_chain(skip_paid=True))
    assert seen["skip_paid"] is True
    assert all(not s["paid"] for s in out["chain"])
    assert out["skip_paid"] is True


def test_a_tenant_namespaced_breaker_lands_on_the_right_provider(monkeypatch):
    monkeypatch.setattr("app.providers.cascade.get_active_providers", lambda **_: ["groq"])
    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers", lambda **_: set()
    )
    monkeypatch.setattr(
        "app.cascade.breaker.default_breaker.snapshot",
        lambda: {"default|groq": {"state": "open"}},
    )
    out = _call(ep.providers_chain())
    assert out["chain"][0]["breaker"] == "open"


# --- title bar ---------------------------------------------------------------


def _title(monkeypatch, *, chain, configured, breakers=None, throttled=(), quota=None,
           byok=frozenset()):
    monkeypatch.setattr("app.providers.cascade.get_active_providers", lambda **_: list(chain))
    monkeypatch.setattr("app.providers.cascade.is_configured", lambda n: n in configured)
    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers", lambda **_: set(byok)
    )
    monkeypatch.setattr("app.cascade.breaker.default_breaker.snapshot", lambda: breakers or {})
    monkeypatch.setattr(
        "app.cascade.quota_meter.is_throttled",
        lambda name, tenant_id=None: (name in throttled, "rpd" if name in throttled else ""),
    )
    if quota is not None:
        monkeypatch.setattr(
            "app.cascade.quota_meter.get_all_status", lambda **_: {"providers": quota}
        )
    return _call(ep.title_status())


def test_the_title_counts_only_providers_that_could_answer_now(monkeypatch):
    """The count is the point: it moves as providers are added, run out, or
    trip. A provider with no key, an open breaker or a throttle cannot answer."""
    out = _title(
        monkeypatch,
        chain=["groq", "cerebras", "cohere", "openrouter"],
        configured={"groq", "cerebras", "cohere"},   # openrouter has no key
        breakers={"default|cerebras": {"state": "open"}},
        throttled={"cohere"},
    )
    assert out["providers"]["ready"] == 1
    assert out["providers"]["names"] == ["groq"]
    assert out["providers"]["total"] == 4


def test_nothing_run_yet_is_not_zero_percent_delegated(monkeypatch):
    """"0% delegated" and "nothing has run yet" are different statements."""
    out = _title(
        monkeypatch, chain=["groq"], configured={"groq"},
        quota={"groq": {"total_requests": 0}},
    )
    assert out["free_share"] is None
    assert out["requests_today"] == 0


def test_the_free_share_is_counted_from_real_requests(monkeypatch):
    out = _title(
        monkeypatch,
        chain=["groq", "anthropic"],
        configured={"groq", "anthropic"},
        quota={"groq": {"total_requests": 7}, "anthropic": {"total_requests": 3}},
    )
    assert out["free_share"] == 70.0
    assert out["requests_today"] == 10


def test_a_broken_provider_lookup_leaves_the_bar_honest(monkeypatch):
    def _boom(**_):
        raise RuntimeError("registry down")

    monkeypatch.setattr("app.providers.cascade.get_active_providers", _boom)
    monkeypatch.setattr(
        "app.multitenant.provider_keys.tenant_configured_providers", lambda **_: set()
    )
    out = _call(ep.title_status())
    assert out["ok"] is False
    assert out["providers"] is None, "unknown must not render as a count"
