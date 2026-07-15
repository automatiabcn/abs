# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Quality pipeline (qual_* / race_*) launcher + step viewer.

POST /v1/panel/pipeline/run     — run a named pipeline for real
GET  /v1/panel/pipeline/recent  — the last N runs with their real steps

Every id the panel offers maps to a pipeline that actually runs in this
product; there is no id here we cannot execute, and the steps shown are the
ones the run produced — never a fixed placeholder.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import current_admin

logger = logging.getLogger(__name__)

# Signed-in operators only — pipeline runs are a record of the company's work.
router = APIRouter(
    prefix="/v1/panel/pipeline", tags=["panel"], dependencies=[Depends(current_admin)]
)

# The four multi-step qual_* pipelines run through the QualResult runner
# (app.pipelines.qual). race_* and the humanize layers run through the
# BasePipeline runner (app.pipelines.race / .humanize). Both are real.
_BASE_PIPELINES = {
    "race",
    "race_code",
    "race_tr",
    "qual_human",
    "qual_code_human",
}

# The full set the panel is allowed to show/run — used to filter Recent runs.
PIPELINE_TOOLS = {
    "qual_code",
    "qual_tr",
    "qual_analysis",
    "qual_translate",
    "qual_human",
    "qual_code_human",
    "race",
    "race_code",
    "race_tr",
}

_RUN_ACTION = "pipeline_run"


def _norm(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class PipelineRunRequest(BaseModel):
    pipeline_id: str = Field(..., min_length=1, max_length=64)
    prompt: str = Field(..., min_length=1, max_length=8000)


def _make_base_pipeline(pipeline_id: str):
    """Instantiate a BasePipeline subclass for a race_* / humanize id."""
    from app.pipelines.humanize.qual_code_human import QualCodeHumanPipeline
    from app.pipelines.humanize.qual_human import QualHumanPipeline
    from app.pipelines.race import (
        RaceCodePipeline,
        RaceGeneralPipeline,
        RaceTrPipeline,
    )

    mapping = {
        "race": RaceGeneralPipeline,
        "race_code": RaceCodePipeline,
        "race_tr": RaceTrPipeline,
        "qual_human": QualHumanPipeline,
        "qual_code_human": QualCodeHumanPipeline,
    }
    return mapping[pipeline_id]()


def _record_run(
    admin: dict, pipeline_id: str, stages: list[dict], elapsed_ms: int
) -> None:
    """Persist a run so Recent runs shows it — with its REAL steps.

    Stored compactly in CustomerAuditEntry.detail (<=512 chars); recent_pipeline
    reads it back rather than inventing latencies.
    """
    from app.customer_audit.logger import log_customer_action

    # Keep only the fields the viewer needs, so the JSON fits the 512-char detail
    # column even for a four-stage pipeline.
    compact = [
        {
            "n": s.get("name", ""),
            "m": s.get("model", ""),
            "ms": int(s.get("elapsed_ms") or 0),
            "ok": bool(s.get("ok")),
        }
        for s in stages
    ]
    detail = json.dumps({"stages": compact, "elapsed_ms": int(elapsed_ms or 0)})
    # The operator has a session but not always a license JTI; the audit helper
    # keys on a non-empty id, so fall back to the subject/"operator".
    jti = str(admin.get("license_jti") or admin.get("sub") or "operator")
    log_customer_action(
        license_jti=jti,
        action=_RUN_ACTION,
        resource=pipeline_id,
        detail=detail[:512],
    )


@router.post("/run")
async def run_pipeline(
    body: PipelineRunRequest, admin: dict = Depends(current_admin)
) -> dict:
    """Run a named pipeline for real and return its completion + real steps."""
    pid = body.pipeline_id
    from app.pipelines.qual import QUAL_HANDLERS, run_qual_pipeline

    completion = ""
    stages: list[dict] = []
    providers: list[str] = []
    verified: Optional[bool] = None
    revisions: Optional[int] = None
    elapsed_ms = 0
    fallback = False
    fallback_reason: Optional[str] = None

    if pid in QUAL_HANDLERS:
        result = await run_qual_pipeline(pid, body.prompt)
        data = result.to_dict()
        completion = data.get("completion", "")
        stages = [
            {
                "name": s.get("name", ""),
                "model": s.get("provider", ""),
                "elapsed_ms": s.get("elapsed_ms", 0),
                "ok": s.get("ok", False),
                "error": s.get("error"),
            }
            for s in data.get("stages", [])
        ]
        providers = list(data.get("providers", []))
        verified = data.get("verified")
        revisions = data.get("revisions")
        elapsed_ms = data.get("elapsed_ms", 0)
        fallback = data.get("fallback", False)
        fallback_reason = data.get("fallback_reason")
    elif pid in _BASE_PIPELINES:
        pipeline = _make_base_pipeline(pid)
        result = await pipeline.run(body.prompt)
        data = result.to_dict()
        completion = data.get("final_response", "")
        stages = [
            {
                "name": s.get("name", ""),
                "model": s.get("model", ""),
                "elapsed_ms": s.get("elapsed_ms", 0),
                "ok": s.get("ok", False),
                "error": s.get("error"),
            }
            for s in data.get("steps", [])
        ]
        providers = [s["model"] for s in stages if s.get("ok") and s.get("model")]
        elapsed_ms = data.get("total_elapsed_ms", 0)
        if data.get("error"):
            fallback = True
            fallback_reason = data.get("error")
    else:
        raise HTTPException(400, f"unknown_pipeline:{pid}")

    if not completion and not fallback:
        # Every provider failed. Say so plainly rather than returning an empty
        # bubble the panel would render as a blank success.
        raise HTTPException(
            502,
            "all_providers_failed: the pipeline ran but no provider produced "
            "a completion — check Provider keys.",
        )

    _record_run(admin, pid, stages, elapsed_ms)

    return {
        "pipeline_id": pid,
        "completion": completion,
        "stages": stages,
        "providers": providers,
        "verified": verified,
        "revisions": revisions,
        "elapsed_ms": elapsed_ms,
        "fallback": fallback,
        "fallback_reason": fallback_reason,
    }


def _parse_stages(detail: Optional[str]) -> tuple[list[dict], Optional[int]]:
    """Read the real steps back out of a stored run. Returns ([], None) for
    older rows that predate step recording — the viewer shows those honestly
    as 'steps not recorded' rather than a fabricated chain."""
    if not detail:
        return [], None
    try:
        payload = json.loads(detail)
    except (ValueError, TypeError):
        return [], None
    raw = payload.get("stages") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return [], None
    steps = [
        {
            "role": s.get("n", ""),
            "model": s.get("m", ""),
            "latency_ms": int(s.get("ms") or 0),
            "ok": bool(s.get("ok")),
        }
        for s in raw
        if isinstance(s, dict)
    ]
    elapsed = payload.get("elapsed_ms") if isinstance(payload, dict) else None
    return steps, (int(elapsed) if isinstance(elapsed, (int, float)) else None)


@router.get("/recent")
async def recent_pipeline(limit: int = 20) -> dict:
    """Recent pipeline runs, newest first, with the steps they actually ran."""
    from sqlmodel import Session, select

    from app.db.models import CustomerAuditEntry
    from app.db.session import get_engine

    capped = max(1, min(int(limit), 500))
    out: list[dict] = []
    with Session(get_engine()) as db:
        # DB-side filter/order/limit — the audit table grows, so never load it
        # whole. Only rows this launcher wrote (action=pipeline_run) carry the
        # real steps; that also naturally scopes out unrelated qual_* audit.
        rows = list(
            db.scalars(
                select(CustomerAuditEntry)
                .where(CustomerAuditEntry.action == _RUN_ACTION)
                .where(CustomerAuditEntry.resource.in_(list(PIPELINE_TOOLS)))
                .order_by(CustomerAuditEntry.ts.desc())
                .limit(capped)
            ).all()
        )
    for r in rows:
        ts = _norm(r.ts)
        steps, elapsed = _parse_stages(r.detail)
        out.append(
            {
                "ts": ts.isoformat() if ts else None,
                "tool": r.resource,
                "elapsed_ms": elapsed,
                # Real steps recorded at run time — [] for pre-recording rows.
                "steps": steps,
            }
        )
        if len(out) >= limit:
            break
    return {"count": len(out), "pipeline_runs": out}
