"""Q8.5 finalize — Admin user management endpoint.

GET /v1/admin/users — list all users for the current tenant.

Closes UX_BUGS US1 (frontend was returning console 404; backend gap).
Frontend (/admin/users page) expects array of user rows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.admin.auth import admin_required

router = APIRouter(prefix="/v1/admin/users", tags=["admin"])


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@router.get("")
async def list_users(_admin: dict = Depends(admin_required)) -> dict:
    from sqlmodel import Session, select

    from app.db.models import User
    from app.db.session import get_engine

    rows: list[dict] = []
    with Session(get_engine()) as session:
        users = session.exec(select(User).order_by(User.created_at.desc())).all()
        for u in users:
            rows.append(
                {
                    "id": u.id,
                    "email": u.email,
                    "role": u.role,
                    "status": u.status,
                    "tenant_slug": u.tenant_slug,
                    "last_login": _iso(u.claimed_at),
                    "created_at": _iso(u.created_at),
                }
            )

    return {"users": rows, "total": len(rows)}
