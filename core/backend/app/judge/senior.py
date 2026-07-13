# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Senior judge — patch scoring from AST metrics plus an LLM opinion.

Combined score is 60% AST fingerprint match, 40% LLM judgment. The LLM leg is
optional: on quota exhaustion or provider error it contributes 0 and the AST
score still stands on its own.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.providers.registry import get_provider
from app.providers.schemas import ProviderError

from .ast_metrics import ast_metrics, extract_added_lines, fingerprint_distance
from .persona import load_persona

logger = logging.getLogger(__name__)


def _ast_score(metrics: Dict[str, float], persona: Dict[str, float]) -> float:
    """AST fingerprint score on a 0-10 scale."""
    if not metrics:
        return 0.0
    distance = fingerprint_distance(metrics, persona)
    # 0 distance → 10, 0.5 distance → 5, 1.0 → 0
    return max(0.0, min(10.0, 10.0 * (1.0 - 2.0 * distance)))


async def _llm_judge(added_code: str) -> Dict[str, Any]:
    """Ask the LLM to grade code quality."""
    if not added_code.strip():
        return {"score": 0.0, "teaching": ""}

    prompt = (
        "Rate this code change from 0 to 10. Criteria: naming, error handling, "
        "readability, minimalism. Answer with short JSON only:\n"
        '{"score": 7.5, "teaching": "1-2 brief suggestions"}\n\n'
        f"CODE:\n{added_code[:4000]}"
    )
    try:
        provider = get_provider("groq")
        resp = await provider.call(prompt, model="openai/gpt-oss-120b", max_tokens=300)
    except (ProviderError, Exception) as exc:  # noqa: BLE001
        logger.info("LLM judge skipped: %s", exc)
        return {"score": 0.0, "teaching": f"LLM quota/err: {str(exc)[:100]}"}

    import json as _json
    import re

    text = resp.text or ""
    # First JSON object in the reply wins; models like to wrap it in prose.
    m = re.search(r"\{[^{}]*\"score\"[^{}]*\}", text, re.DOTALL)
    if not m:
        return {"score": 0.0, "teaching": text[:200]}
    try:
        parsed = _json.loads(m.group(0))
        score = float(parsed.get("score", 0.0))
        teaching = str(parsed.get("teaching", ""))[:400]
        return {"score": max(0.0, min(10.0, score)), "teaching": teaching}
    except Exception:
        return {"score": 0.0, "teaching": text[:200]}


async def judge_diff(diff_text: str, file_path: Optional[str] = None) -> Dict[str, Any]:
    """Score a diff (60% AST + 40% LLM) and return the teaching notes."""
    added_code = extract_added_lines(diff_text)
    is_python = bool(file_path and file_path.endswith(".py"))

    metrics = ast_metrics(added_code) if is_python else {}
    persona = load_persona()
    ast_s = _ast_score(metrics, persona) if metrics else 0.0

    llm = await _llm_judge(added_code)
    llm_s = float(llm.get("score", 0.0))

    if metrics:
        combined = round(0.6 * ast_s + 0.4 * llm_s, 2)
    else:
        combined = round(llm_s, 2)

    teaching_lines: List[str] = []
    if metrics:
        for k in ("docstring_ratio", "type_hints_ratio"):
            actual = metrics.get(k, 0.0)
            target = persona.get(k, 0.0)
            delta = abs(actual - target)
            if delta > 0.2:
                teaching_lines.append(
                    f"{k}: {actual:.2f} vs target {target:.2f} (delta {delta:.2f})"
                )
    if llm.get("teaching"):
        teaching_lines.append(f"LLM: {llm['teaching']}")

    result = {
        "combined_score": combined,
        "ast_score": round(ast_s, 2) if metrics else None,
        "llm_score": round(llm_s, 2),
        "added_lines": len(added_code.splitlines()),
        "fingerprint_details": [
            {"metric": k, "actual": metrics.get(k, 0.0), "target": persona.get(k, 0.0)}
            for k in ("docstring_ratio", "type_hints_ratio", "avg_func_lines")
            if metrics
        ],
        "teaching": teaching_lines,
    }

    # Judgment logging is best-effort: an unavailable log must not fail a judge.
    try:
        from .log import log_judgment as _log

        result["judgment_id"] = _log(result, file_path=file_path, source="judge_diff")
    except Exception as exc:
        logger.info("judge_log skipped: %s", exc)

    return result
