"""Phase 1 / S19-close — Workflow synthesis + execute HTTP surface.

POST /v1/workflows/synthesize  intent → JSON workflow (template-matched
                                 fallback when no LLM key, full
                                 `synthesizer.synthesize` when available).
POST /v1/workflows/execute     dry_run plan or queue via runner stub.
GET  /v1/workflows/jobs/{id}   poll runner state.

Auth: panel session (`current_admin`).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import current_admin
from app.services import feature_usage as feature_usage_service
from app.workflow_v10 import runner
from app.workflow_v10.builder.synthesizer import (
    SynthesisError,
    extract_json,
    synthesize as synth_run,
)
from app.workflow_v10.builder.templates import list_templates
from app.workflow_v10.builder.validator import validate_workflow

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])
logger = logging.getLogger(__name__)


# ---------- request / response models -------------------------------------


class SynthesizeRequest(BaseModel):
    intent: str = Field(..., min_length=10, max_length=2000)
    locale: str = "tr"


class SynthesizeResponse(BaseModel):
    workflow: Dict[str, Any]
    explanation: str
    warnings: List[str] = []
    revisions: int = 0
    source: str = "template"  # "llm" when LLM-backed


class ExecuteRequest(BaseModel):
    workflow: Dict[str, Any]
    dry_run: bool = True


# ---------- synthesizer wiring --------------------------------------------


_INTENT_KEYWORDS = (
    ("slack", "slack"),
    ("linear", "linear"),
    ("gmail", "gmail"),
    ("email", "gmail"),
    ("e-posta", "gmail"),
    ("notion", "notion"),
    ("github", "github"),
    ("rag", "rag"),
    ("transkrip", "meeting"),
    ("toplant", "meeting"),
    ("ses", "tts"),
    ("seslendir", "tts"),
)


def _template_fallback(intent: str, locale: str) -> Dict[str, Any]:
    """Pick the closest-matching template by keyword. Returns
    {workflow, explanation, source='template'}."""
    intent_lower = intent.lower()
    templates = list_templates()
    if not templates:
        raise SynthesisError("no_templates_loaded")

    best = templates[0]
    best_score = 0
    for tmpl in templates:
        score = 0
        haystack = (
            (tmpl.title_en or "")
            + " "
            + (getattr(tmpl, "title_tr", "") or "")
            + " "
            + " ".join(getattr(tmpl, "tags", []) or [])
        ).lower()
        for kw, _ in _INTENT_KEYWORDS:
            if kw in intent_lower and kw in haystack:
                score += 2
        if score > best_score:
            best, best_score = tmpl, score

    workflow = best.workflow.model_dump(mode="json")
    workflow.setdefault("metadata", {})["template_id"] = best.id
    workflow["metadata"]["intent"] = intent
    workflow["metadata"]["locale"] = locale
    explanation = (
        f"Template fallback: matched '{best.id}' ({best_score} kw hits). "
        "No LLM key wired — Sprint Q2.CO4 promotes this to a real ragas-judged synth."
    )
    return {
        "workflow": workflow,
        "explanation": explanation,
        "source": "template",
        "revisions": 0,
    }


async def _llm_synth_fn(prompt: str) -> str:
    """Optional LLM-backed synth. Raises if no provider available so caller
    can fall back to template-match."""
    raise SynthesisError("llm_provider_not_wired")


# ---------- endpoints ------------------------------------------------------


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(
    body: SynthesizeRequest, admin: dict = Depends(current_admin)
) -> SynthesizeResponse:
    use_llm = os.environ.get("ABS_WORKFLOW_LLM_ENABLED", "false").lower() == "true"
    if use_llm:
        try:
            result = await synth_run(
                body.intent, synth_fn=_llm_synth_fn, locale=body.locale
            )
            payload = {
                "workflow": result.workflow.model_dump(mode="json"),
                "explanation": "LLM-synthesised workflow",
                "source": "llm",
                "revisions": result.revisions,
            }
        except SynthesisError as exc:
            logger.warning("LLM synth failed (%s); falling back to template", exc)
            payload = _template_fallback(body.intent, body.locale)
    else:
        payload = _template_fallback(body.intent, body.locale)

    report = validate_workflow(payload["workflow"])
    warnings = [
        f"{label}: {msg}"
        for label, items in (("warning", report.warnings), ("error", report.errors))
        for msg in items
    ]

    try:
        feature_usage_service.increment(
            "workflow_run", actor_email=admin.get("sub")
        )
    except Exception:
        pass

    return SynthesizeResponse(
        workflow=payload["workflow"],
        explanation=payload["explanation"],
        warnings=warnings,
        revisions=payload.get("revisions", 0),
        source=payload.get("source", "template"),
    )


@router.post("/execute")
async def execute(
    body: ExecuteRequest, admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    if not body.workflow.get("nodes"):
        raise HTTPException(400, "workflow.nodes required")

    plan_steps = runner.plan(body.workflow)
    if body.dry_run:
        return {
            "status": "dry_run_ok",
            "steps": plan_steps,
            "estimate_s": runner.estimate(plan_steps),
        }
    job_id = await runner.enqueue(
        body.workflow, tenant_slug=admin.get("sub", "default")
    )
    return {
        "status": "queued",
        "job_id": job_id,
        "steps": plan_steps,
        "estimate_s": runner.estimate(plan_steps),
    }


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: str, _admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    state = runner.status(job_id)
    if state is None:
        raise HTTPException(404, "job_not_found")
    return state
