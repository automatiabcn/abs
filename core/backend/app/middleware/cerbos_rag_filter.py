# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""T-012 — Cerbos RAG resource pre-filter.

FastAPI dependency that resolves the caller's tenant to a `rag_collection`
resource and asks Cerbos for a decision BEFORE any Qdrant work runs. Failure
of the PDP is treated as DENY by the underlying `cerbos_client`.
"""

from __future__ import annotations

import logging

from cerbos.sdk.client import CerbosClient
from fastapi import Depends, HTTPException, status

from app.api.v1.deps import (
    AuthContext,
    get_admin_or_bearer_auth_context,
    get_cerbos_client,
)
from app.auth.cerbos_client import build_resource, is_allowed

logger = logging.getLogger(__name__)

__all__ = ["RAGAuth", "rag_action_dep"]

_RAG_COLLECTION_KIND = "rag_collection"


class RAGAuth:
    """Pairs the decoded principal with the RAG collection resource id."""

    __slots__ = ("auth", "tenant_id", "resource_id")

    def __init__(self, auth: AuthContext, tenant_id: str, resource_id: str) -> None:
        self.auth = auth
        self.tenant_id = tenant_id
        self.resource_id = resource_id


def rag_action_dep(action: str):
    """Build a FastAPI dependency that enforces a Cerbos decision for *action*."""

    def _dep(
        auth: AuthContext = Depends(get_admin_or_bearer_auth_context),
        cerbos: CerbosClient = Depends(get_cerbos_client),
    ) -> RAGAuth:
        tenant = (auth.tenant_id or "").strip()
        if not tenant:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="missing_tenant_claim"
            )
        resource_id = f"{tenant}-rag"
        principal = auth.as_principal()
        resource = build_resource(
            resource_id, _RAG_COLLECTION_KIND, tenant_id=tenant
        )
        if not is_allowed(principal, resource, action, client=cerbos):
            logger.info(
                "rag_cerbos_denied subject=%s tenant=%s action=%s",
                auth.subject,
                tenant,
                action,
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="forbidden_rag_action"
            )
        return RAGAuth(auth=auth, tenant_id=tenant, resource_id=resource_id)

    return _dep
