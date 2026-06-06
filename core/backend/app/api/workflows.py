# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Phase 1 / S19-close — Workflow synthesis + execute HTTP surface.

POST /v1/workflows/synthesize  intent → JSON workflow (template-matched
                                 fallback when no LLM key, full
                                 `synthesizer.synthesize` when available).
POST /v1/workflows/execute     dry_run plan or queue via runner stub.
GET  /v1/workflows/jobs/{id}   poll runner state.

Auth: panel session (`current_admin`).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

from app.db.models import SavedWorkflow
from app.db.session import get_engine

from app.api.auth import current_admin
from app.cascade.orchestrator import call_with_cascade
from app.providers.cascade import get_active_providers
from app.providers.schemas import ProviderError
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


# Q12-L25-002 — workflow execute boundary caps. Pre-fix, ExecuteRequest
# accepted `workflow: Dict[str, Any]` with no nodes-count cap and no
# raw-payload cap, so an attacker (admin-auth'd or compromised JWT)
# could POST a 10k-node / multi-MB payload. runner.plan() walks the
# whole structure, allocates per-node, and OOMs the worker. Same
# family as Q12-L25-001 (R17 marketplace InstallBody UNBOUNDED).
WORKFLOW_NODES_MAX = 200       # generous; KOBİ templates ship with 5–20
WORKFLOW_EDGES_MAX = 500       # ≈ 2.5× nodes (DAG fan-out budget)


class ExecuteRequest(BaseModel):
    workflow: Dict[str, Any]
    dry_run: bool = True

    @model_validator(mode="after")
    def _cap_workflow_size(self) -> "ExecuteRequest":
        wf = self.workflow or {}
        nodes = wf.get("nodes")
        if nodes is not None:
            if not isinstance(nodes, list):
                raise ValueError("workflow.nodes must be a list")
            if len(nodes) > WORKFLOW_NODES_MAX:
                raise ValueError(
                    f"workflow.nodes count exceeds cap "
                    f"({len(nodes)} > {WORKFLOW_NODES_MAX})"
                )
        edges = wf.get("edges")
        if edges is not None:
            if not isinstance(edges, list):
                raise ValueError("workflow.edges must be a list")
            if len(edges) > WORKFLOW_EDGES_MAX:
                raise ValueError(
                    f"workflow.edges count exceeds cap "
                    f"({len(edges)} > {WORKFLOW_EDGES_MAX})"
                )
        return self


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


async def _cascade_synth_fn(prompt: str) -> str:
    """LLM-backed synth via the cascade. Picks the first active provider
    and asks for the workflow JSON. Raises `SynthesisError` when no
    provider is configured or all transient-fail so the caller falls
    back to the keyword-matched template."""
    active = get_active_providers()
    if not active:
        raise SynthesisError("no_providers_configured")
    primary, *fallbacks = active
    try:
        resp = await call_with_cascade(
            prompt,
            primary=primary,
            fallbacks=tuple(fallbacks),
            use_cache=True,
            max_tokens=2048,
        )
    except ProviderError as exc:
        raise SynthesisError(
            f"cascade_failed: {exc.message or str(exc)}"
        ) from exc
    if not resp.text:
        raise SynthesisError("cascade_empty_response")
    return resp.text


# Default LLM hook for the route — overridable in tests via monkeypatch.
_llm_synth_fn = _cascade_synth_fn


# ---------- endpoints ------------------------------------------------------


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(
    body: SynthesizeRequest, admin: dict = Depends(current_admin)
) -> SynthesizeResponse:
    # Founder Tester Round 2 (BUG-5) — LLM-first via cascade. Disable only
    # when the operator explicitly opts out (`ABS_WORKFLOW_LLM_ENABLED=false`)
    # or when the cascade chain is empty; the latter check happens inside
    # `_cascade_synth_fn` and surfaces as `SynthesisError`.
    use_llm = os.environ.get("ABS_WORKFLOW_LLM_ENABLED", "true").lower() == "true"
    payload: Dict[str, Any]
    fallback_warning: Optional[str] = None
    if use_llm:
        try:
            # Sprint 2B BUG-31 — synth_run already retries up to
            # max_revisions+1 times on parse / validation errors. Cap at
            # 1 retry (so 2 attempts total) so we don't multiply LLM
            # cost when the cascade is just returning bad JSON; the
            # template fallback below covers the remaining tail.
            result = await synth_run(
                body.intent,
                synth_fn=_llm_synth_fn,
                locale=body.locale,
                max_revisions=1,
            )
            payload = {
                "workflow": result.workflow.model_dump(mode="json"),
                "explanation": (
                    f"LLM-synthesised workflow "
                    f"(revisions={result.revisions})"
                ),
                "source": "llm",
                "revisions": result.revisions,
            }
        except SynthesisError as exc:
            logger.warning("LLM synth failed (%s); falling back to template", exc)
            payload = _template_fallback(body.intent, body.locale)
            payload["explanation"] = (
                f"Template fallback after LLM failure: {exc}. "
                f"{payload['explanation']}"
            )
            # Sprint 2B BUG-31 — surface a soft warning so the panel
            # can show a toast ("LLM çıktısı doğrulanamadı; şablon
            # eşleşmesi gösteriliyor") instead of the operator seeing
            # the canvas silently revert without any explanation.
            fallback_warning = (
                "LLM synthesis failed, using template match — "
                f"{type(exc).__name__}: {str(exc)[:120]}"
            )
    else:
        payload = _template_fallback(body.intent, body.locale)

    report = validate_workflow(payload["workflow"])
    warnings = [
        f"{label}: {msg}"
        for label, items in (("warning", report.warnings), ("error", report.errors))
        for msg in items
    ]
    if fallback_warning:
        warnings.insert(0, fallback_warning)

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
    estimated_cost_usd = runner.estimate_cost(plan_steps)
    # BUG-V2 — strip the embedded node from the response so the public
    # surface stays the same shape the panel canvas already binds to.
    public_steps = [{k: v for k, v in s.items() if k != "node"} for s in plan_steps]
    if body.dry_run:
        return {
            "status": "dry_run_ok",
            "steps": public_steps,
            "estimate_s": runner.estimate(plan_steps),
            "estimated_cost_usd": estimated_cost_usd,
        }
    job_id = await runner.enqueue(
        body.workflow, tenant_slug=admin.get("sub", "default")
    )
    return {
        "status": "queued",
        "job_id": job_id,
        "steps": public_steps,
        "estimate_s": runner.estimate(plan_steps),
        "estimated_cost_usd": estimated_cost_usd,
    }


def _job_owner_matches(state: Dict[str, Any], admin: dict) -> bool:
    """A job is owned by the admin identity that enqueued it (execute keys the
    job by ``admin.sub``). Cross-tenant callers must not read or resume it.

    Backwards-compatible: in single-tenant/dev every admin resolves to the same
    key ("default" when no sub), so existing single-tenant flows are unaffected;
    isolation engages once admins carry distinct subjects.
    """
    return state.get("tenant_slug") == admin.get("sub", "default")


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: str, admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    state = runner.status(job_id)
    # 404 (not 403) on a cross-tenant job so its existence isn't disclosed.
    if state is None or not _job_owner_matches(state, admin):
        raise HTTPException(404, "job_not_found")
    return state


class ResumeRequest(BaseModel):
    approved: bool


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: str, body: ResumeRequest, admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    """Approve or reject a workflow paused at a human-in-the-loop (hitl) node."""
    # Ownership gate BEFORE resuming — a cross-tenant admin must never be able
    # to approve/reject another tenant's hitl gate (e.g. a destructive op).
    state = runner.status(job_id)
    if state is None or not _job_owner_matches(state, admin):
        raise HTTPException(404, "job_not_found")
    result = await runner.resume(
        job_id, approved=body.approved, role=admin.get("sub")
    )
    if result is None:
        raise HTTPException(404, "job_not_found")
    if "error" in result:
        raise HTTPException(409, result["error"])
    return result


# ---------- saved workflow definitions (reusable library) -----------------
# synthesize/execute/jobs handle ad-hoc runs; these persist a named workflow
# so the Builder's "Save" actually stores something the operator can reload.


class SaveWorkflowBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    definition: Dict[str, Any]


def _wf_tenant(admin: dict) -> str:
    # Same tenant resolution as the rest of the panel (users table → slug,
    # else "default"). Lazy import avoids a circular import at module load.
    from app.api.chat import _resolve_tenant

    return _resolve_tenant(admin.get("sub", "")) or "default"


def _serialize_saved_wf(row: SavedWorkflow) -> Dict[str, Any]:
    try:
        defn = json.loads(row.definition_json)
    except (ValueError, TypeError):
        defn = {}
    return {
        "id": row.id,
        "name": row.name,
        "definition": defn,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.post("/definitions", status_code=201)
def save_workflow_definition(
    body: SaveWorkflowBody, admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    """Persist a named workflow definition for the caller's tenant."""
    tenant = _wf_tenant(admin)
    row = SavedWorkflow(
        tenant_slug=tenant,
        name=body.name.strip(),
        definition_json=json.dumps(body.definition, ensure_ascii=False),
        created_by=admin.get("sub", ""),
    )
    with Session(get_engine()) as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        return _serialize_saved_wf(row)


@router.get("/definitions")
def list_workflow_definitions(
    admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    """List the caller tenant's saved workflows (most-recent first)."""
    tenant = _wf_tenant(admin)
    with Session(get_engine()) as db:
        rows = list(
            db.exec(
                select(SavedWorkflow)
                .where(SavedWorkflow.tenant_slug == tenant)
                .order_by(SavedWorkflow.updated_at.desc())
                .limit(200)
            )
        )
        return {
            "workflows": [_serialize_saved_wf(r) for r in rows],
            "count": len(rows),
        }


@router.get("/definitions/{wf_id}")
def get_workflow_definition(
    wf_id: int, admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    tenant = _wf_tenant(admin)
    with Session(get_engine()) as db:
        row = db.get(SavedWorkflow, wf_id)
        # Tenant gate: never expose another tenant's saved workflow.
        if row is None or row.tenant_slug != tenant:
            raise HTTPException(404, "workflow_not_found")
        return _serialize_saved_wf(row)


@router.put("/definitions/{wf_id}")
def update_workflow_definition(
    wf_id: int, body: SaveWorkflowBody, admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    """Update a saved workflow in place (so re-saving a loaded workflow doesn't
    create a duplicate row). Tenant-gated."""
    tenant = _wf_tenant(admin)
    with Session(get_engine()) as db:
        row = db.get(SavedWorkflow, wf_id)
        if row is None or row.tenant_slug != tenant:
            raise HTTPException(404, "workflow_not_found")
        row.name = body.name.strip()
        row.definition_json = json.dumps(body.definition, ensure_ascii=False)
        row.updated_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
        db.refresh(row)
        return _serialize_saved_wf(row)


@router.delete("/definitions/{wf_id}", status_code=204)
def delete_workflow_definition(
    wf_id: int, admin: dict = Depends(current_admin)
) -> None:
    tenant = _wf_tenant(admin)
    with Session(get_engine()) as db:
        row = db.get(SavedWorkflow, wf_id)
        if row is None or row.tenant_slug != tenant:
            raise HTTPException(404, "workflow_not_found")
        db.delete(row)
        db.commit()
    return None
