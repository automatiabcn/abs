"""`/v1/workflows/synthesize` LLM-first.

Replaces the prior template-only fallback with a real LLM call routed through
`call_with_cascade`. This test suite covers the route contract:

1. LLM returns valid workflow JSON → response.source == "llm".
2. LLM unavailable / cascade fails → graceful template fallback (200, source==
   "template").
3. LLM returns invalid JSON → after retries, still falls back to template.
4. Locale variants (TR, EN, ES) all return 200 with a workflow.

We monkeypatch the route's `_llm_synth_fn` so the tests are hermetic — no
provider HTTP calls fire.
"""

from __future__ import annotations

import json

import pytest


_VALID_LLM_WORKFLOW = {
    "id": "llm-synth-demo",
    "name": "Slack notify on Stripe payment failure",
    "description": "Test workflow synthesised by mocked LLM",
    "locale": "en",
    "tenant_scoped": True,
    "trigger": {
        "kind": "event",
        "id": "trg-llm-synth-demo",
        "event_topic": "abs.stripe.payment_failed",
        "description": "Stripe failure event",
    },
    "nodes": [
        {
            "id": "n1",
            "kind": "abs_tool",
            "name": "Slack notify",
            "config": {
                "tool_name": "abs.slack_post",
                "tool_args": {"channel": "#payments"},
            },
        },
    ],
    "edges": [],
    "variables": [],
    "tags": ["slack", "stripe"],
}


@pytest.fixture()
def admin_client(client, monkeypatch):
    monkeypatch.setenv("ABS_WORKFLOW_LLM_ENABLED", "true")
    r = client.post(
        "/auth/login",
        json={"email": "admin@local", "password": "CHANGEME"},
    )
    assert r.status_code == 200, r.text
    return client


def test_llm_first_returns_source_llm(admin_client, monkeypatch):
    """Happy path — LLM returns valid JSON → source=llm."""

    async def _fake_llm(prompt: str) -> str:
        return json.dumps(_VALID_LLM_WORKFLOW)

    monkeypatch.setattr("app.api.workflows._llm_synth_fn", _fake_llm)

    r = admin_client.post(
        "/v1/workflows/synthesize",
        json={
            "intent": "Send Slack message when a Stripe payment fails",
            "locale": "en",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "llm", body
    assert body["workflow"]["name"] == "Slack notify on Stripe payment failure"
    assert body["revisions"] == 0
    assert "No LLM key wired" not in body["explanation"]


def test_template_fallback_when_cascade_unavailable(admin_client, monkeypatch):
    """LLM raises SynthesisError → graceful 200 + source=template."""
    from app.workflow_v10.builder.synthesizer import SynthesisError

    async def _no_provider(prompt: str) -> str:
        raise SynthesisError("no_providers_configured")

    monkeypatch.setattr("app.api.workflows._llm_synth_fn", _no_provider)

    r = admin_client.post(
        "/v1/workflows/synthesize",
        json={
            "intent": "Müşteri toplantı kaydı geldiğinde transcribe et + Slack özet",
            "locale": "tr",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "template", body
    assert "Template fallback" in body["explanation"]
    # The workflow must still be valid + non-empty.
    assert body["workflow"]["nodes"], body


def test_invalid_llm_json_falls_back_to_template(admin_client, monkeypatch):
    """LLM returns garbage every retry → falls back to template, no 500."""

    async def _bad_json(prompt: str) -> str:
        return "this is not JSON at all"

    monkeypatch.setattr("app.api.workflows._llm_synth_fn", _bad_json)

    r = admin_client.post(
        "/v1/workflows/synthesize",
        json={
            "intent": "Send a daily summary to Slack at 9am",
            "locale": "en",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "template", body


@pytest.mark.parametrize(
    "locale,intent",
    [
        ("en", "Send Slack message when a Stripe payment fails"),
        ("tr", "Stripe ödeme başarısız olduğunda Slack mesajı gönder"),
        ("es", "Enviar mensaje de Slack cuando falle un pago de Stripe"),
    ],
)
def test_locale_variants_succeed(admin_client, monkeypatch, locale, intent):
    """All 3 supported locales must reach 200 + non-empty workflow."""

    captured = {}

    async def _fake_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        wf = dict(_VALID_LLM_WORKFLOW, locale=locale)
        return json.dumps(wf)

    monkeypatch.setattr("app.api.workflows._llm_synth_fn", _fake_llm)

    r = admin_client.post(
        "/v1/workflows/synthesize",
        json={"intent": intent, "locale": locale},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "llm"
    assert body["workflow"]["nodes"], body
    # Synthesizer prompt should carry the locale tag.
    assert f"({locale})" in captured["prompt"]


def test_disabled_workflow_llm_uses_template(admin_client, monkeypatch):
    """`ABS_WORKFLOW_LLM_ENABLED=false` → template path, never calls LLM."""
    monkeypatch.setenv("ABS_WORKFLOW_LLM_ENABLED", "false")
    called = {"count": 0}

    async def _should_not_run(prompt: str) -> str:
        called["count"] += 1
        return "{}"

    monkeypatch.setattr("app.api.workflows._llm_synth_fn", _should_not_run)

    r = admin_client.post(
        "/v1/workflows/synthesize",
        json={
            "intent": "Send Slack message when a Stripe payment fails",
            "locale": "en",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "template"
    assert called["count"] == 0
