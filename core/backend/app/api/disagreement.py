# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The most recent second opinion, for the operator's dashboard.

This was a stub returning a fixed empty payload — the shape was final and
nothing ever filled it, which is a widget that reads as broken forever. It now
serves the last `ask_disagree` run of this session.

The answers themselves are left out. This is a status readout, and one
developer's question does not belong on an operator's dashboard.

"Nothing has been asked yet" and "the models disagreed" are different states
and are worded differently: an empty widget with no explanation cannot be told
apart from a failed one, which is why the stub carried a note to begin with.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from app.api.auth import current_admin
from app.disagreement.detector import last_run

router = APIRouter(prefix="/api/disagreement", tags=["disagreement"])


@router.get("/latest")
async def get_latest_disagreement(_admin: dict = Depends(current_admin)) -> dict:
    tenant: Optional[str] = None
    try:
        tenant = str(_admin.get("tenant") or "") or None
    except Exception:  # noqa: BLE001 — an odd claim set is not a reason to 500
        tenant = None

    run = last_run(tenant)
    if not run:
        return {
            "status": "empty",
            "last_call_at": None,
            "models": [],
            "matrix": [],
            "consensus_score": None,
            "note": "No second opinion has been asked for yet this session.",
        }
    return {
        "status": run.get("status", "empty"),
        "last_call_at": run.get("last_call_at"),
        "asked": run.get("asked", []),
        "models": run.get("models", []),
        "matrix": run.get("similarity_matrix", []),
        "consensus_score": run.get("consensus_score"),
        "consensus_level": run.get("consensus_level", "none"),
        "similarity_basis": run.get("similarity_basis", "none"),
        "note": run.get("note", ""),
    }
