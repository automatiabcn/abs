# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""/v1/capture — auto-capture: send a bot to a live meeting and record it.

  POST /v1/capture/jobs              → 201, schedule a meeting link for capture
  GET  /v1/capture/jobs              → list this tenant's jobs (status refreshed)
  GET  /v1/capture/jobs/{job_id}     → one job (status refreshed)
  POST /v1/capture/jobs/{job_id}/cancel → best-effort cancel

Phase 2, slice 1: a person pastes a Meet/Zoom/Teams link (a connected calendar
feeds these automatically later) and a bot is dispatched to join and record.

Honesty: `recorder_live` tells the surface whether a *real* recorder is wired
(the `local` side-car or a `recall` key). On the default `mock` backend it is
false — the job is accepted and scheduled but no audio is captured, and the UI
says "simulated" instead of pretending a recording exists.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import current_admin
from app.api.meetings import _admin_tenant
from app.db.models import CaptureJob
from app.meeting.bot_recall import RecallBudgetExceeded
from app.meeting.capture_service import (
    cancel_capture_job,
    create_capture_job,
    get_capture_job,
    list_capture_jobs,
    refresh_status,
)
from app.observability.audit import emit_event

router = APIRouter(prefix="/v1/capture", tags=["capture"])
logger = logging.getLogger(__name__)

# Backends that actually record audio. On anything else the job is a scheduled
# placeholder — surfaced as such, never dressed up as a live recording.
_LIVE_BACKENDS = {"local", "recall"}


class CreateCaptureJob(BaseModel):
    meeting_url: str = Field(..., min_length=1, max_length=1024)
    title: str = Field("", max_length=256)
    duration_minutes: int = Field(60, ge=5, le=480)


def _serialize(job: CaptureJob) -> Dict[str, Any]:
    return {
        "job_id": job.job_id,
        "meeting_url": job.meeting_url,
        "platform": job.platform,
        "title": job.title,
        "status": job.status,
        "bot_backend": job.bot_backend,
        # Honest: is a real recorder behind this, or a mock placeholder?
        "recorder_live": (job.bot_backend or "") in _LIVE_BACKENDS,
        "estimated_cost_usd": round(job.estimated_cost_usd or 0.0, 4),
        "error_message": job.error_message,
        "scheduled_start": (
            job.scheduled_start.isoformat() if job.scheduled_start else None
        ),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "meeting_id": job.meeting_id,
    }


@router.post("/jobs", status_code=201)
def create_job(
    body: CreateCaptureJob,
    admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    tenant = _admin_tenant(admin)
    created_by = str(admin.get("sub") or "")
    try:
        job = create_capture_job(
            tenant_slug=tenant,
            created_by=created_by,
            meeting_url=body.meeting_url,
            title=body.title,
            duration_minutes=body.duration_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RecallBudgetExceeded as exc:  # defensive — service already traps this
        raise HTTPException(status_code=429, detail=f"budget: {exc}") from exc

    emit_event(
        None,
        action="capture.job.created",
        outcome="success",
        resource_type="capture_job",
        resource_id=job.job_id,
        user_id=created_by,
        tenant_id=tenant,
        provider=job.bot_backend,
        reason=job.status,
    )
    return _serialize(job)


@router.get("/jobs")
def list_jobs(admin: dict = Depends(current_admin)) -> Dict[str, Any]:
    tenant = _admin_tenant(admin)
    jobs = [refresh_status(j) for j in list_capture_jobs(tenant)]
    return {
        "jobs": [_serialize(j) for j in jobs],
        # One flag the surface can trust for the whole panel: is capture real
        # here, or is every job a simulation on the mock backend?
        "recorder_available": any(
            (j.bot_backend or "") in _LIVE_BACKENDS for j in jobs
        ),
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str, admin: dict = Depends(current_admin)) -> Dict[str, Any]:
    tenant = _admin_tenant(admin)
    job = get_capture_job(job_id)
    if job is None or job.tenant_slug != tenant:
        raise HTTPException(status_code=404, detail="capture job not found")
    return _serialize(refresh_status(job))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, admin: dict = Depends(current_admin)) -> Dict[str, Any]:
    tenant = _admin_tenant(admin)
    existing = get_capture_job(job_id)
    if existing is None or existing.tenant_slug != tenant:
        raise HTTPException(status_code=404, detail="capture job not found")
    job = cancel_capture_job(job_id)
    assert job is not None  # existence just checked under the same tenant
    emit_event(
        None,
        action="capture.job.cancelled",
        outcome="success",
        resource_type="capture_job",
        resource_id=job_id,
        user_id=str(admin.get("sub") or ""),
        tenant_id=tenant,
        reason=job.status,
    )
    return _serialize(job)
