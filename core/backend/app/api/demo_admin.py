# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Demo admin endpoint: reset the demo countdown.

POST /v1/admin/demo/reset
  Header: Authorization: Bearer <ABS_ADMIN_TOKEN>
  → 204 No Content (idempotent: same result whether state existed or not)

Missing credentials: 401. Wrong token: 403.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.auth.bearer import extract_bearer, token_matches
from app.config import settings

router = APIRouter(prefix="/v1/admin", tags=["admin"])
logger = logging.getLogger(__name__)


def _check_admin(authorization: str | None) -> None:
    token = extract_bearer(authorization)
    if not token_matches(token, settings.admin_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token",
        )


@router.post("/demo/reset", status_code=status.HTTP_200_OK)
async def reset_demo(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_admin(authorization)

    state_path = Path(settings.data_dir) / "demo_state.json"
    existed = state_path.is_file()
    if existed:
        try:
            state_path.unlink()
        except Exception as exc:
            logger.exception("demo state delete failed: %s", exc)
            raise HTTPException(
                status_code=500, detail=f"Silinemedi: {str(exc)[:200]}"
            )

    logger.info("[admin] demo reset existed=%s", existed)
    return JSONResponse(
        status_code=200,
        content={"ok": True, "existed_before": existed, "state_path": str(state_path)},
    )
