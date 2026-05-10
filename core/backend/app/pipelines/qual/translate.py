# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""qual_translate: translate -> back-translate -> drift check -> retry."""

from __future__ import annotations

import json

from . import runner as _runner
from ._json import extract_json

_TRANSLATE_SYSTEM = (
    "Aşağıdaki metni doğal ve akıcı bir şekilde çevir. "
    "Yorum yapma, yalnızca çeviriyi döndür."
)
_BACK_TRANSLATE_SYSTEM = (
    "Translate the following text back into the original language. "
    "Return ONLY the translation, no commentary."
)
_DRIFT_SYSTEM = (
    "Compare the original text and the back-translation. Report a JSON "
    "object {\"score\": float between 0 and 1, "
    "\"issues\": [\"...\"]} where score=1 means identical meaning."
)
_RETRY_SYSTEM = (
    "Re-translate the source text taking the issues into account. "
    "Return only the new translation."
)


def _split_request(prompt: str) -> tuple[str, str]:
    lower = prompt.lower()
    delim_idx = -1
    for sep in (":", "—", "-"):
        idx = prompt.find(sep)
        if idx != -1 and idx < 80:
            delim_idx = idx
            break
    if delim_idx == -1:
        return "English", prompt
    instruction = prompt[:delim_idx]
    source = prompt[delim_idx + 1 :].strip()
    target = "English"
    if "ingilizce" in lower or "english" in lower:
        target = "English"
    elif "türkçe" in lower or "turkish" in lower:
        target = "Turkish"
    elif "ispanyolca" in lower or "spanish" in lower or "español" in lower:
        target = "Spanish"
    elif "almanca" in lower or "german" in lower:
        target = "German"
    return target, source or instruction


async def execute(prompt: str, call_provider: _runner.CallProvider) -> _runner.QualResult:
    result = _runner.QualResult(pipeline_id="qual_translate", completion="", verified=False)
    target_lang, source = _split_request(prompt)

    translate_prompt = (
        f"{_TRANSLATE_SYSTEM}\n\nHedef dil: {target_lang}\n\nMetin:\n{source[:5000]}"
    )
    t_stage, translation = await _runner.run_stage(
        "qual_translate", "translate", "groq", translate_prompt, call_provider=call_provider
    )
    result.stages.append(t_stage)
    if t_stage.ok:
        result.providers.append(t_stage.provider)

    if not t_stage.ok or not translation:
        from .runner import _fallback_single_provider

        result.completion = await _fallback_single_provider(prompt)
        result.fallback = True
        result.fallback_reason = "translate_failed"
        return result

    back_prompt = (
        f"{_BACK_TRANSLATE_SYSTEM}\n\nText:\n{translation[:5000]}"
    )
    b_stage, back = await _runner.run_stage(
        "qual_translate", "back-translate", "cerebras", back_prompt, call_provider=call_provider
    )
    if not b_stage.ok:
        b_stage, back = await _runner.run_stage(
            "qual_translate", "back-translate", "groq", back_prompt, call_provider=call_provider
        )
    result.stages.append(b_stage)
    if b_stage.ok:
        result.providers.append(b_stage.provider)

    if not b_stage.ok or not back:
        result.completion = translation
        result.verified = False
        return result

    drift_prompt = (
        f"{_DRIFT_SYSTEM}\n\nORIGINAL:\n{source[:3000]}\n\n"
        f"BACK_TRANSLATION:\n{back[:3000]}"
    )
    d_stage, drift_raw = await _runner.run_stage(
        "qual_translate", "drift", "groq", drift_prompt, call_provider=call_provider
    )
    result.stages.append(d_stage)
    drift = extract_json(drift_raw, default={"score": 1.0, "issues": []})
    if not isinstance(drift, dict):
        drift = {"score": 1.0, "issues": []}
    score = float(drift.get("score") or 1.0)
    issues = drift.get("issues") or []

    if score >= 0.7:
        result.completion = translation
        result.verified = True
        return result

    retry_prompt = (
        f"{_RETRY_SYSTEM}\n\nTarget language: {target_lang}\n\n"
        f"SOURCE:\n{source[:5000]}\n\n"
        f"PREVIOUS TRANSLATION:\n{translation[:3000]}\n\n"
        f"ISSUES:\n{json.dumps(issues, ensure_ascii=False)[:1500]}"
    )
    r_stage, retried = await _runner.run_stage(
        "qual_translate", "retry", "groq", retry_prompt, call_provider=call_provider
    )
    result.stages.append(r_stage)
    if r_stage.ok and retried:
        result.completion = retried
        result.providers.append(r_stage.provider)
        result.verified = True
        result.revisions = 1
    else:
        result.completion = translation
        result.verified = False
    return result


_runner._register("qual_translate", execute)
