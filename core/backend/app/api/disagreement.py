# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Model anlaşmazlık (disagreement) latest endpoint'i (stub).

Gerçek ask_disagree çıktıları 008-ask-disagree task'ında bağlanacak.
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
        "note": "Gerçek ask_disagree çıktıları 008-ask-disagree task'ında bağlanacak",
    }
