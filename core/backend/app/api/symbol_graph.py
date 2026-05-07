# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""016 — Symbol graph endpoints (real implementation).

Python AST parsed sembolleri SQLite store'dan sorgular.
Endpoint'ler:
  GET  /api/symbol-graph/neighbors?name=X&depth=N
  GET  /api/symbol-graph/search?q=X[&kind=function|class|import]
  GET  /api/symbol-graph/stats
  POST /api/symbol-graph/index   body: {"path": "...", "replace": false}
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.auth import current_admin

router = APIRouter(prefix="/api/symbol-graph", tags=["symbol-graph"])


@router.get("/neighbors")
async def get_neighbors(
    name: str = Query(..., min_length=1, max_length=256),
    depth: int = Query(1, ge=1, le=5),
    _admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    from app.symbols.store import neighbors

    return neighbors(name, depth=depth)


@router.get("/search")
async def search_symbols(
    q: str = Query(..., min_length=1, max_length=128),
    kind: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    _admin: dict = Depends(current_admin),
) -> Dict[str, Any]:
    from app.symbols.store import search

    return {"query": q, "kind": kind, "results": search(q, limit=limit, kind=kind)}


@router.get("/stats")
async def get_stats(_admin: dict = Depends(current_admin)) -> Dict[str, Any]:
    from app.symbols.store import stats

    return stats()


class IndexRequest(BaseModel):
    path: str = Field(..., min_length=1)
    replace: bool = False


@router.post("/index")
async def post_index(
    body: IndexRequest, _admin: dict = Depends(current_admin)
) -> Dict[str, Any]:
    from app.symbols.index import index_path

    return index_path(body.path, replace=body.replace)
