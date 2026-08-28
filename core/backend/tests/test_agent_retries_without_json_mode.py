"""When JSON mode makes the model hallucinate a tool call, ask again in plain text.

G1, 2026-08-28: in JSON mode gpt-oss answered the outbound_draft prompt
with `{"name":"graph","arguments":…}` — a tool call to a tool it was never
given — and Groq rejected it (400 tool_use_failed) on every try. The agent
now asks once more without response_format and with the rule spelled out;
the runtime's parser reads fenced or plain JSON either way.
"""

from __future__ import annotations

import pytest

from app.agents import runtime
from app.providers.schemas import CascadeUnavailable, ProviderError, ProviderResponse

REJECT = 'groq 400: {"error":{"message":"Tool choice is none, but model called a tool","code":"tool_use_failed","failed_generation":"{\\"name\\": \\"graph\\"}"}}'


@pytest.mark.asyncio
async def test_json_mode_rejection_falls_back_to_plain_text(monkeypatch):
    calls = []

    async def _cascade(prompt, **kw):
        calls.append(kw.get("response_format"))
        if kw.get("response_format"):
            raise CascadeUnavailable(
                "every provider in the chain failed; some may recover shortly",
                providers_tried=["groq"],
                last_error=ProviderError(REJECT, provider="groq", transient=True),
            )
        assert "do not call any tool" in prompt
        return ProviderResponse(text='{"summary":"Draft ready","confidence":0.7,"recommended_action":"send","payload":{}}', provider="groq", model="m", elapsed_ms=1)

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _cascade)
    monkeypatch.setattr("app.providers.cascade.get_active_providers", lambda **kw: ["groq"])

    async def _no_evidence(*a, **kw):
        return []

    monkeypatch.setattr(runtime, "_gather_evidence", _no_evidence)
    r = await runtime.run_agent("outbound_draft", "draft the renewal email", tenant_id="t_json_1")
    assert calls == [{"type": "json_object"}, None]
    assert r.degraded is False
    assert r.held is False
    assert r.requires_approval is True


@pytest.mark.asyncio
async def test_a_non_generation_failure_is_not_retried(monkeypatch):
    calls = []

    async def _cascade(prompt, **kw):
        calls.append(1)
        raise ProviderError("groq 401: invalid api key", provider="groq", transient=False)

    monkeypatch.setattr("app.cascade.orchestrator.call_with_cascade", _cascade)
    monkeypatch.setattr("app.providers.cascade.get_active_providers", lambda **kw: ["groq"])

    async def _no_evidence(*a, **kw):
        return []

    monkeypatch.setattr(runtime, "_gather_evidence", _no_evidence)
    r = await runtime.run_agent("outbound_draft", "draft the renewal email", tenant_id="t_json_2")
    assert len(calls) == 1
    assert r.degraded is True and r.held is True
