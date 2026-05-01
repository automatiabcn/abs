"""029 Modul B — GDPR data export (Article 15) HTTP endpoints.

POST /v1/me/data-export             — start async export job
GET  /v1/me/data-export/{job_id}    — status + (when ready) download URL
GET  /v1/me/data-export/{job_id}/download — encrypted ZIP bytes
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select

from app.customer_audit.data_export import create_export_job, run_export_job
from app.customer_audit.logger import log_customer_action
from app.db.models import DataExportJob, License
from app.db.session import get_engine
from app.licensing import verify_license

router = APIRouter(prefix="/v1/me", tags=["me"])
logger = logging.getLogger(__name__)


def _verify_bearer_license(authorization: Optional[str]) -> tuple[str, str]:
    """Returns (jti, customer_email) or raises 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authorization Bearer license required")
    token = authorization.split(None, 1)[1].strip()
    try:
        payload = verify_license(token)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(401, f"License verify failed: {exc}") from exc
    jti = payload.get("jti")
    if not jti:
        raise HTTPException(401, "Token missing jti")
    with Session(get_engine()) as db:
        row = db.scalars(select(License).where(License.jti == jti)).first()
        email = row.customer_email if row else ""
    return jti, email


@router.post("/data-export")
async def start_data_export(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Kicks off a synchronous-ish export build (small in MVP)."""
    jti, email = _verify_bearer_license(authorization)
    job = create_export_job(license_jti=jti, customer_email=email)
    result = run_export_job(job.job_id)
    log_customer_action(
        license_jti=jti,
        action="data_export.requested",
        resource=job.job_id,
        detail=f"size={result.get('size', 0)}",
    )
    return {
        "job_id": job.job_id,
        "status": "done" if result.get("ok") else "failed",
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
    }


@router.get("/data-export/{job_id}")
async def get_data_export_status(
    job_id: str,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    jti, _ = _verify_bearer_license(authorization)
    with Session(get_engine()) as db:
        row = db.scalars(
            select(DataExportJob).where(DataExportJob.job_id == job_id)
        ).first()
        if row is None:
            raise HTTPException(404, "job_not_found")
        if row.license_jti != jti:
            raise HTTPException(403, "not_owner")
        out = {
            "job_id": row.job_id,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "size_bytes": None,
        }
        if row.output_path:
            try:
                out["size_bytes"] = Path(row.output_path).stat().st_size
            except OSError:
                out["size_bytes"] = None
            out["download_url"] = f"/v1/me/data-export/{row.job_id}/download"
    return out


@router.get("/data-export/{job_id}/download")
async def download_data_export(
    job_id: str,
    authorization: Optional[str] = Header(default=None),
) -> Response:
    jti, _ = _verify_bearer_license(authorization)
    with Session(get_engine()) as db:
        row = db.scalars(
            select(DataExportJob).where(DataExportJob.job_id == job_id)
        ).first()
        if row is None:
            raise HTTPException(404, "job_not_found")
        if row.license_jti != jti:
            raise HTTPException(403, "not_owner")
        if row.status != "done" or not row.output_path:
            raise HTTPException(409, "not_ready")
        expires_at = row.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                raise HTTPException(410, "expired")
        path = Path(row.output_path)
        if not path.exists():
            raise HTTPException(404, "file_missing")
    data = path.read_bytes()
    log_customer_action(
        license_jti=jti,
        action="data_export.downloaded",
        resource=job_id,
        detail=f"size={len(data)}",
    )
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{job_id}.zip.enc"',
        },
    )
