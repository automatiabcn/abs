# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""qual_analysis: 3-perspective parallel -> synthesis."""

from __future__ import annotations

import asyncio

from . import runner as _runner

_PERSPECTIVE_TEMPLATE = (
    "Write a short, clear analysis of the request below from your own point of "
    "view. Give only your own answer; do not compare yourself to other models."
    "\n\nREQUEST:\n{prompt}"
)
_SYNTH_SYSTEM = (
    "Merge the analyses from three different models into one balanced answer. "
    "Keep the trade-off each perspective raises, state where they agree, and "
    "label contradictions explicitly. Answer in the language the user used."
)


async def execute(prompt: str, call_provider: _runner.CallProvider) -> _runner.QualResult:
    result = _runner.QualResult(pipeline_id="qual_analysis", completion="", verified=False)

    base = _PERSPECTIVE_TEMPLATE.format(prompt=prompt)
    a, b, c = await asyncio.gather(
        _runner.run_stage(
            "qual_analysis", "perspective-a", "groq", base, call_provider=call_provider
        ),
        _runner.run_stage(
            "qual_analysis", "perspective-b", "cerebras", base, call_provider=call_provider
        ),
        _runner.run_stage(
            "qual_analysis", "perspective-c", "gemini", base, call_provider=call_provider
        ),
    )
    result.stages.extend([a[0], b[0], c[0]])
    survivors = [(s, t) for s, t in (a, b, c) if s.ok and t]
    result.providers.extend(s.provider for s, _ in survivors)

    if not survivors:
        from .runner import _fallback_single_provider

        result.completion = await _fallback_single_provider(prompt)
        result.fallback = True
        result.fallback_reason = "all_perspectives_failed"
        return result

    if len(survivors) == 1:
        result.completion = survivors[0][1]
        result.verified = True
        return result

    perspectives_block = "\n\n".join(
        f"### {stage.provider}\n{text[:3000]}" for stage, text in survivors
    )
    synth_prompt = (
        f"{_SYNTH_SYSTEM}\n\nUSER REQUEST:\n{prompt}\n\n"
        f"PERSPECTIVES:\n{perspectives_block}"
    )
    synth_stage, synth_text = await _runner.run_stage(
        "qual_analysis", "synthesize", "groq", synth_prompt, call_provider=call_provider
    )
    result.stages.append(synth_stage)
    if synth_stage.ok and synth_text:
        result.completion = synth_text
        result.providers.append(synth_stage.provider)
        result.verified = True
        result.revisions = 1
    else:
        survivors.sort(key=lambda c: len(c[1]), reverse=True)
        result.completion = survivors[0][1]
        result.verified = False
    return result


_runner._register("qual_analysis", execute)
