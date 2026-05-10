# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""qual_tr: parallel generate -> grammar review -> polish."""

from __future__ import annotations

import asyncio
import json

from . import runner as _runner
from ._json import extract_json

_GEN_SYSTEM = (
    "Akıcı, doğal bir Türkçe yazı yaz. Diline gereksiz İngilizce karıştırma, "
    "kullanıcının sorusuna doğrudan cevap ver."
)
_REVIEW_SYSTEM = (
    "Aşağıdaki Türkçe metinde gramer, anlatım bozukluğu, yabancı dil "
    "karışması veya tutarsızlık varsa bul. SADECE JSON listesi olarak "
    "[{\"issue\": str, \"suggestion\": str}] döndür; sorun yoksa []."
)
_POLISH_SYSTEM = (
    "Aşağıdaki Türkçe metni listelenen sorunlara göre yeniden yaz. "
    "Sadece düzeltilmiş metni döndür; meta yorum ekleme."
)


async def execute(prompt: str, call_provider: _runner.CallProvider) -> _runner.QualResult:
    result = _runner.QualResult(pipeline_id="qual_tr", completion="", verified=False)

    gen_prompt = f"{_GEN_SYSTEM}\n\nİstek:\n{prompt}"
    primary, secondary = await asyncio.gather(
        _runner.run_stage(
            "qual_tr", "generate-primary", "groq", gen_prompt, call_provider=call_provider
        ),
        _runner.run_stage(
            "qual_tr", "generate-secondary", "gemini", gen_prompt, call_provider=call_provider
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

    review_prompt = f"{_REVIEW_SYSTEM}\n\nMetin:\n{draft[:5000]}"
    review_stage, review_raw = await _runner.run_stage(
        "qual_tr", "review", "groq", review_prompt, call_provider=call_provider
    )
    result.stages.append(review_stage)
    if review_stage.ok:
        result.providers.append(review_stage.provider)

    issues = extract_json(review_raw, default=[])
    if not isinstance(issues, list):
        issues = []

    if not issues:
        result.completion = draft
        result.verified = True
        return result

    polish_prompt = (
        f"{_POLISH_SYSTEM}\n\n"
        f"SORUNLAR:\n{json.dumps(issues, ensure_ascii=False)[:1500]}\n\n"
        f"METİN:\n{draft[:5000]}"
    )
    polish_stage, polished = await _runner.run_stage(
        "qual_tr", "polish", "cerebras", polish_prompt, call_provider=call_provider
    )
    if not polish_stage.ok:
        polish_stage, polished = await _runner.run_stage(
            "qual_tr", "polish", "groq", polish_prompt, call_provider=call_provider
        )
    result.stages.append(polish_stage)
    if polish_stage.ok and polished:
        result.completion = polished
        result.providers.append(polish_stage.provider)
        result.verified = True
        result.revisions = 1
    else:
        result.completion = draft
        result.verified = False
    return result


_runner._register("qual_tr", execute)
