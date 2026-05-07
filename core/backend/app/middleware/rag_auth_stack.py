# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-014 — RAG gateway auth/authz stack (organisational re-export).

The actual middleware/dependency wiring lives in T-005 and T-012:
    `get_auth_context` (JWT verify + tenant claim parse, X-ABS-Audience honored)
    `get_cerbos_client` (app-state singleton PDP client)
    `rag_action_dep("ingest"|"query"|"delete")` (Cerbos resource pre-check)

This module exposes those names from a single import path so future
gateway-level concerns (rate-limit, request id, token scope) can be added
here without rewiring callers.
"""

from __future__ import annotations

from app.api.v1.deps import AuthContext, get_auth_context, get_cerbos_client
from app.middleware.cerbos_rag_filter import RAGAuth, rag_action_dep

__all__ = [
    "AuthContext",
    "RAGAuth",
    "get_auth_context",
    "get_cerbos_client",
    "rag_action_dep",
]
