# Copyright (c) 2026 Automatia BCN. All rights reserved.
"""qual_* multi-model pipeline behaviour."""

from __future__ import annotations

import json

import pytest

from app.pipelines.qual import QUAL_HANDLERS, QualResult, run_qual_pipeline
from app.pipelines.qual import runner as runner_mod
from app.pipelines.qual._json import extract_json


@pytest.fixture(autouse=True)
def _stub_cascade_fallback(monkeypatch):
    async def fake(prompt: str) -> str:
        return "[fallback]"

    monkeypatch.setattr(runner_mod, "_fallback_single_provider", fake)
    yield


def test_handlers_register_all_four():
    assert set(QUAL_HANDLERS.keys()) == {
        "qual_code",
        "qual_tr",
        "qual_analysis",
        "qual_translate",
    }


def test_extract_json_handles_fenced_block():
    raw = 'Here is the review:\n```json\n[{"issue": "missing import"}]\n```\nthanks'
    parsed = extract_json(raw, default=[])
    assert parsed == [{"issue": "missing import"}]


def test_extract_json_handles_balanced_braces_with_nested_strings():
    raw = 'Result: {"text": "a } string with brace", "score": 0.5} cheers'
    parsed = extract_json(raw, default={})
    assert parsed == {"text": "a } string with brace", "score": 0.5}


def test_extract_json_returns_default_on_garbage():
    assert extract_json("not json at all", default="fallback") == "fallback"


@pytest.mark.asyncio
async def test_qual_code_no_issues_skips_fix_stage():
    async def call(provider, prompt):
        if "JSON list" in prompt or "Reply with ONLY" in prompt:
            return "[]"
        return "def add(a, b):\n    return a + b\n"

    result = await run_qual_pipeline("qual_code", "write add", call_provider=call)
    assert isinstance(result, QualResult)
    assert result.completion.startswith("def add")
    assert result.verified is True
    assert result.revisions == 0
    assert not any(s.name == "fix" for s in result.stages)


@pytest.mark.asyncio
async def test_qual_code_verify_finds_issues_triggers_fix():
    issues = [{"issue": "missing import json", "line": 1}]

    async def call(provider, prompt):
        if "Reply with ONLY a JSON" in prompt:
            return json.dumps(issues)
        if "Repair the code" in prompt or "Return ONLY the corrected" in prompt:
            return "import json\n\ndef parse(s):\n    return json.loads(s)\n"
        return "def parse(s):\n    return json.loads(s)\n"

    result = await run_qual_pipeline("qual_code", "parse json", call_provider=call)
    assert result.verified is True
    assert result.revisions == 1
    assert result.completion.startswith("import json")
    assert any(s.name == "fix" for s in result.stages)


@pytest.mark.asyncio
async def test_qual_code_all_generators_fail_falls_back():
    async def call(provider, prompt):
        raise RuntimeError("provider boom")

    result = await run_qual_pipeline("qual_code", "write something", call_provider=call)
    assert result.fallback is True
    assert result.completion == "[fallback]"


@pytest.mark.asyncio
async def test_qual_tr_polish_runs_on_review_issues():
    review_payload = json.dumps([{"issue": "yabancı kelime", "suggestion": "öneri"}])

    async def call(provider, prompt):
        # Route on the stage's system prompt: polish, then review, else draft.
        if "Rewrite the Turkish text" in prompt:
            return "Daha akıcı türkçe versiyon."
        if "JSON list" in prompt or "grammar errors" in prompt:
            return review_payload
        return "Bu bir taslak Türkçe metindir."

    result = await run_qual_pipeline("qual_tr", "Bunu Türkçe yaz", call_provider=call)
    assert result.verified is True
    assert result.revisions == 1
    assert "akıcı" in result.completion


@pytest.mark.asyncio
async def test_qual_analysis_three_perspectives_are_synthesised():
    async def call(provider, prompt):
        # The synthesis stage is the one carrying the merge instruction.
        if "Merge the analyses" in prompt:
            return "Sentez: hız, kalite, esneklik karışımı."
        return f"{provider}-perspective-text"

    result = await run_qual_pipeline(
        "qual_analysis", "React vs Vue analiz", call_provider=call
    )
    assert result.verified is True
    assert "Sentez" in result.completion
    perspective_names = {
        s.name for s in result.stages if s.name.startswith("perspective")
    }
    assert perspective_names == {"perspective-a", "perspective-b", "perspective-c"}


@pytest.mark.asyncio
async def test_qual_analysis_one_survivor_skips_synthesis():
    async def call(provider, prompt):
        if "birleştir" in prompt or "Üç farklı" in prompt:
            raise AssertionError("synthesis must be skipped")
        if provider == "groq":
            return "Tek perspektif metni."
        raise RuntimeError("provider down")

    result = await run_qual_pipeline(
        "qual_analysis", "tek bakış aç", call_provider=call
    )
    assert result.completion == "Tek perspektif metni."
    assert result.revisions == 0


@pytest.mark.asyncio
async def test_qual_translate_drift_below_threshold_triggers_retry():
    drift_payload = json.dumps({"score": 0.4, "issues": ["meaning loss"]})
    call_count = {"translate": 0, "retry": 0}

    async def call(provider, prompt):
        if prompt.startswith("Compare the original"):
            return drift_payload
        if prompt.startswith("Translate the following text back"):
            return "Geri çeviri taslağı."
        if "Re-translate the source" in prompt:
            call_count["retry"] += 1
            return "Final clean retry translation."
        if "Aşağıdaki metni" in prompt or "Hedef dil:" in prompt:
            call_count["translate"] += 1
            return "Initial translation rough."
        return ""

    result = await run_qual_pipeline(
        "qual_translate",
        "Translate to English: Bu bir denemedir.",
        call_provider=call,
    )
    assert call_count["retry"] == 1
    assert result.completion.startswith("Final clean")
    assert result.revisions == 1


@pytest.mark.asyncio
async def test_qual_translate_drift_above_threshold_keeps_first_translation():
    drift_payload = json.dumps({"score": 0.95, "issues": []})

    async def call(provider, prompt):
        if prompt.startswith("Compare the original"):
            return drift_payload
        if prompt.startswith("Translate the following text back"):
            return "Bu bir denemedir."
        if "Aşağıdaki metni" in prompt or "Hedef dil:" in prompt:
            return "This is a test."
        return ""

    result = await run_qual_pipeline(
        "qual_translate",
        "Translate to English: Bu bir denemedir.",
        call_provider=call,
    )
    assert result.completion == "This is a test."
    assert result.revisions == 0
    assert result.verified is True


@pytest.mark.asyncio
async def test_unknown_pipeline_returns_fallback():
    result = await run_qual_pipeline("qual_doesnt_exist", "hi")
    assert result.fallback is True
    assert result.completion == "[fallback]"
