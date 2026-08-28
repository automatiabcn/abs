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

from app.providers.byok import owner_key_for

from .ast_metrics import ast_metrics, extract_added_lines, fingerprint_distance
from .persona import load_persona

# ONE model, several providers. Scores are only comparable across runs if the
# same model produced them, so the fallback changes the server, never the
# judge. Spellings differ per provider; both are gpt-oss-120b.
_JUDGE_ROUTES: tuple[tuple[str, str], ...] = (
    ("groq", "openai/gpt-oss-120b"),
    ("cerebras", "gpt-oss-120b"),
)


def _book(resp, *, provider: str, tenant_id, model: str, exc=None) -> None:
    """The judge's calls reach the same books as the cascade's."""
    try:
        from app.cascade.orchestrator import record_direct_call

        record_direct_call(resp, provider=provider, tenant_id=tenant_id, model=model, exc=exc)
    except Exception:  # noqa: BLE001
        pass


def _server_has_key(provider: str) -> bool:
    """Whether the operator configured this provider globally."""
    try:
        from app.providers.cascade import is_configured

        return bool(is_configured(provider))
    except Exception:  # noqa: BLE001 — an unknown answer is "do not try it"
        return False

logger = logging.getLogger(__name__)


def _ast_score(metrics: Dict[str, float], persona: Dict[str, float]) -> float:
    """AST fingerprint score on a 0-10 scale."""
    if not metrics:
        return 0.0
    distance = fingerprint_distance(metrics, persona)
    # 0 distance → 10, 0.5 distance → 5, 1.0 → 0
    return max(0.0, min(10.0, 10.0 * (1.0 - 2.0 * distance)))


async def _llm_judge(
    added_code: str,
    diff_text: Optional[str] = None,
    file_path: Optional[str] = None,
    *,
    tenant_id: Optional[str] = None,
    user_subject: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask the LLM to grade the CHANGE — the diff, not an orphan fragment.

    Grading added lines alone systematically under-scores correct edits: a
    one-line ``return 2`` shown without what it replaced has no naming to judge
    and no error handling to check, so it reads as a snippet with everything
    missing (the live editor tour scored exactly such a change 2/10). Given the
    unified diff and the file it lands in, the score answers the question the
    editor actually puts on every proposal: is this a good change?
    """
    if not added_code.strip():
        # Nothing to judge is UNKNOWN, not a zero — a 0.0 here flows into
        # judgment logs and stats as "worst possible code" for an empty diff.
        return {"score": None, "teaching": "no added lines to judge"}

    where = f" to `{file_path}`" if file_path else ""
    if diff_text and diff_text.strip():
        subject = f"UNIFIED DIFF{where}:\n{diff_text[:4000]}"
    else:
        subject = f"ADDED CODE{where}:\n{added_code[:4000]}"
    prompt = (
        "You are reviewing one code change. Rate the CHANGE from 0 to 10 — not "
        "how complete the snippet looks on its own. A small, correct, minimal "
        "edit deserves a high score; judge naming, error handling, readability "
        "and minimalism only where the change actually touches them. Answer "
        "with short JSON only:\n"
        '{"score": 7.5, "teaching": "1-2 brief suggestions"}\n\n'
        f"{subject}"
    )
    # The judge was pinned to one provider's groq key. Two ways that ends in
    # "not graded" on a working install: the operator's groq quota runs out,
    # or the install is BYOK-only and has no server groq key at all — and the
    # Review panel then reports every file as unjudged (08-01 audit).
    #
    # The MODEL, though, is not interchangeable: scores are only comparable
    # across runs if the same model produces them (v5/v6 judge work). So the
    # fallback keeps gpt-oss-120b and only changes WHO serves it — measured
    # live on cerebras, which returns the same JSON shape.
    resp = None
    last_error = ""
    for provider_name, model_id in _JUDGE_ROUTES:
        api_key = owner_key_for(
            provider_name, tenant_slug=tenant_id, user_subject=user_subject
        )
        if not (api_key or _server_has_key(provider_name)):
            continue
        try:
            provider = get_provider(provider_name)
            call_kwargs = {"api_key": api_key} if api_key else {}
            # Room for the diff-aware answer. At 300 the reply was truncated
            # mid-string, the JSON never closed, and a real 6 was recorded as a
            # 0 — which read as "this file scored below 5" in the review panel.
            resp = await provider.call(
                prompt, model=model_id, max_tokens=1200, **call_kwargs
            )
            _book(resp, provider=provider_name, tenant_id=tenant_id, model=model_id)
            break
        except (ProviderError, Exception) as exc:  # noqa: BLE001
            last_error = str(exc)[:100]
            _book(None, provider=provider_name, tenant_id=tenant_id, model=model_id, exc=exc)
            logger.info("LLM judge on %s skipped: %s", provider_name, exc)
    if resp is None:
        return {"score": None, "teaching": f"LLM unavailable: {last_error or 'no judge provider'}"}

    text = resp.text or ""
    score, teaching = _parse_judgement(text)
    if score is None:
        # Unusable output is UNKNOWN, never zero. A failed judgement scored as
        # 0 is worse than no judgement: it accuses code the judge never read.
        logger.info("LLM judge produced no usable score: %r", text[:200])
        return {"score": None, "teaching": text[:200]}
    return {"score": score, "teaching": teaching}


def _parse_judgement(text: str) -> tuple[Optional[float], str]:
    """Pull (score, teaching) out of a model reply.

    Models wrap the object in prose, and a long answer can be cut off before
    its closing brace. A truncated reply still carries the number we asked for,
    so the score is salvaged from `"score": N` directly when the object does
    not parse — otherwise a complete judgement is thrown away over a missing
    character.
    """
    import json as _json
    import re

    if not text.strip():
        return None, ""
    match = re.search(r"\{[^{}]*\"score\"[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            parsed = _json.loads(match.group(0))
            raw = float(parsed.get("score"))
            return max(0.0, min(10.0, raw)), str(parsed.get("teaching", ""))[:400]
        except (TypeError, ValueError):
            pass
    loose = re.search(r'"score"\s*:\s*(-?\d+(?:\.\d+)?)', text)
    if not loose:
        return None, ""
    salvaged = max(0.0, min(10.0, float(loose.group(1))))
    note = re.search(r'"teaching"\s*:\s*"([^"]*)', text)
    return salvaged, (note.group(1)[:400] if note else "")


async def judge_diff(
    diff_text: str,
    file_path: Optional[str] = None,
    *,
    tenant_id: Optional[str] = None,
    user_subject: Optional[str] = None,
) -> Dict[str, Any]:
    """Score a diff (60% AST + 40% LLM) and return the teaching notes."""
    added_code = extract_added_lines(diff_text)
    is_python = bool(file_path and file_path.endswith(".py"))

    metrics = ast_metrics(added_code) if is_python else {}
    persona = load_persona()
    ast_s = _ast_score(metrics, persona) if metrics else 0.0

    llm = await _llm_judge(
        added_code,
        diff_text=diff_text,
        file_path=file_path,
        tenant_id=tenant_id,
        user_subject=user_subject,
    )
    raw_llm = llm.get("score")
    llm_s: Optional[float] = float(raw_llm) if raw_llm is not None else None

    # An unavailable model leg is not a zero. Grade on what was actually
    # measured: both legs when both ran, the AST alone when the model did not
    # answer, and NOTHING (None) when neither could judge — the caller renders
    # that as ungraded, which is the truth.
    if metrics and llm_s is not None:
        combined: Optional[float] = round(0.6 * ast_s + 0.4 * llm_s, 2)
    elif metrics:
        combined = round(ast_s, 2)
    elif llm_s is not None:
        combined = round(llm_s, 2)
    else:
        combined = None

    teaching_lines: List[str] = []
    if metrics:
        for k in ("docstring_ratio", "type_hints_ratio"):
            if k not in metrics:
                continue  # the diff adds no function; the ratio does not apply
            actual = metrics[k]
            target = persona.get(k, 0.0)
            delta = abs(actual - target)
            if delta > 0.2:
                teaching_lines.append(
                    f"{k}: {actual:.2f} vs target {target:.2f} (delta {delta:.2f})"
                )
    if llm.get("teaching"):
        teaching_lines.append(f"LLM: {llm['teaching']}")

    if llm_s is None:
        teaching_lines.append(
            "the model leg did not answer — this score is the AST fingerprint "
            "alone" if metrics else "no judgement was possible for this change"
        )

    result = {
        "combined_score": combined,
        "ast_score": round(ast_s, 2) if metrics else None,
        "llm_score": round(llm_s, 2) if llm_s is not None else None,
        "added_lines": len(added_code.splitlines()),
        "fingerprint_details": [
            {"metric": k, "actual": metrics[k], "target": persona.get(k, 0.0)}
            for k in ("docstring_ratio", "type_hints_ratio", "avg_func_lines")
            if metrics and k in metrics
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


async def judge_file(file_path: str) -> Dict[str, Any]:
    """Grade a whole file as if every line were newly added.

    A convenience over :func:`judge_diff` for the editor's "grade this file"
    action: the file content is wrapped as an all-added pseudo-diff and run
    through the same AST + LLM pipeline.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError as exc:
        # A file the judge could not read is ungraded, not the worst file in
        # the repo. 0.0 here would sort it to the top of the review panel and
        # count as a low score in every consumer downstream.
        return {
            "combined_score": None,
            "ast_score": None,
            "llm_score": None,
            "added_lines": 0,
            "fingerprint_details": [],
            "teaching": [f"read error: {exc} — not graded"],
        }

    pseudo_diff = "\n".join("+" + line for line in content.splitlines())
    return await judge_diff(pseudo_diff, file_path)
