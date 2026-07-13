# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Latest model-disagreement endpoint (stub).

Shape is final; it stays empty until ask_disagree results are fed in.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import current_admin

router = APIRouter(prefix="/api/disagreement", tags=["disagreement"])


@router.get("/latest")
async def get_latest_disagreement(_admin: dict = Depends(current_admin)) -> dict:
    return {
        "status": "empty",
        "last_call_at": None,
        "models": [],
        "matrix": [],
        "consensus_score": None,
        "note": "Live ask_disagree results are not wired up yet",
    }
