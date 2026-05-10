# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""qual_code: parallel generate -> verify -> fix."""

from __future__ import annotations

import asyncio
import json

from . import runner as _runner
from ._json import extract_json

_GEN_SYSTEM = (
    "You are a careful senior engineer. Write working code. "
    "Prefer the simplest correct solution; include only the code in your reply."
)
_VERIFY_SYSTEM = (
    "Review the following code for bugs, missing imports, off-by-one errors, "
    "type errors, and obvious security issues. "
    "Reply with ONLY a JSON list of {\"issue\": str, \"line\": int|null} entries; "
    "empty list `[]` if the code is correct."
)
_FIX_SYSTEM = (
    "Repair the code below given the listed issues. "
    "Return ONLY the corrected code, no commentary."
)


async def execute(prompt: str, call_provider: _runner.CallProvider) -> _runner.QualResult:
    result = _runner.QualResult(pipeline_id="qual_code", completion="", verified=False)

    gen_prompt = f"{_GEN_SYSTEM}\n\nTask:\n{prompt}"
    primary, secondary = await asyncio.gather(
        _runner.run_stage(
            "qual_code", "generate-primary", "groq", gen_prompt, call_provider=call_provider
        ),
        _runner.run_stage(
            "qual_code", "generate-secondary", "cerebras", gen_prompt, call_provider=call_provider
        ),
    )
    result.stages.extend([primary[0], secondary[0]])
    result.providers.extend(s.provider for s in (primary[0], secondary[0]) if s.ok)

    candidates = [(s, t) for s, t in (primary, secondary) if s.ok and t]
    if not candidates:
        from .runner import _fallback_single_provider

        result.completion = await _fallback_single_provider(prompt)
        result.fallback = True
        result.fallback_reason = "both_generators_failed"
        return result

    candidates.sort(key=lambda c: len(c[1]), reverse=True)
    _, draft = candidates[0]

    verify_prompt = f"{_VERIFY_SYSTEM}\n\nCode:\n{draft[:6000]}"
    verify_stage, verify_raw = await _runner.run_stage(
        "qual_code", "verify", "groq", verify_prompt, call_provider=call_provider
    )
    result.stages.append(verify_stage)
    if verify_stage.ok:
        result.providers.append(verify_stage.provider)

    issues = extract_json(verify_raw, default=[])
    if not isinstance(issues, list):
        issues = []

    if not issues:
        result.completion = draft
        result.verified = True
        return result

    fix_prompt = (
        f"{_FIX_SYSTEM}\n\n"
        f"ISSUES:\n{json.dumps(issues, ensure_ascii=False)[:1500]}\n\n"
        f"CODE:\n{draft[:6000]}"
    )
    fix_stage, fixed = await _runner.run_stage(
        "qual_code", "fix", "groq", fix_prompt, call_provider=call_provider
    )
    result.stages.append(fix_stage)
    if fix_stage.ok and fixed:
        result.completion = fixed
        result.providers.append(fix_stage.provider)
        result.verified = True
        result.revisions = 1
    else:
        result.completion = draft
        result.verified = False
    return result


_runner._register("qual_code", execute)
