"""qual_code's verify leg does not require a local Ollama.

Activity panel, live 2026-08-28 (G21): "Run chain" produced a draft in 1.1 s
and then died at step 2 — "OLLAMA_URL is not configured — no local Ollama" —
on an install without Ollama, which is every first install. The verifier is
local codellama when Ollama is configured and Groq's small model otherwise.
"""

from __future__ import annotations

import pytest

import app.pipelines.quality.code as qc


@pytest.mark.asyncio
async def test_without_ollama_the_verify_leg_runs_on_groq(monkeypatch):
    calls: list[tuple[str, str]] = []

    class _P:
        def __init__(self, name):
            self.name = name

        async def call(self, prompt, model=None, **kw):
            calls.append((self.name, model))
            from tests.test_pipelines_quality import _make_resp

            return _make_resp("PASS" if "Review this code" in prompt else "def f():\n    return 1\n", model=model or "?", provider=self.name)

    monkeypatch.setattr(qc, "get_provider", lambda name: _P(name))
    monkeypatch.setattr("app.providers.cascade.is_configured", lambda name: False)
    result = await qc.QualCodePipeline().run("write f")
    names = [s.name for s in result.steps]
    assert "verify" in names
    verify = next(s for s in result.steps if s.name == "verify")
    assert verify.ok, verify
    assert ("groq", "openai/gpt-oss-20b") in calls
    assert not any(n == "ollama" for n, _ in calls)
    assert result.final_response.startswith("def f")


@pytest.mark.asyncio
async def test_with_ollama_the_verify_leg_stays_local(monkeypatch):
    calls: list[tuple[str, str]] = []

    class _P:
        def __init__(self, name):
            self.name = name

        async def call(self, prompt, model=None, **kw):
            calls.append((self.name, model))
            from tests.test_pipelines_quality import _make_resp

            return _make_resp("PASS", model=model or "?", provider=self.name)

    monkeypatch.setattr(qc, "get_provider", lambda name: _P(name))
    monkeypatch.setattr("app.providers.cascade.is_configured", lambda name: name == "ollama")
    await qc.QualCodePipeline().run("write f")
    assert ("ollama", "codellama:7b") in calls
