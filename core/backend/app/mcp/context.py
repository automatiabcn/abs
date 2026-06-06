# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Request-scoped MCP caller context (multi-tenant Phase 1, W3).

The MCP transport auth middleware validates a bearer token that already
carries `tenant` + `actor` (the minting user). Those are stashed here in
ContextVars so MCP tool functions can forward them to `call_with_cascade` and
per-owner provider keys (BYOK) apply to delegated calls — without changing the
MCP protocol. Same async-safe pattern as the RLS `current_tenant` ContextVar.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

mcp_tenant_id: ContextVar[Optional[str]] = ContextVar("mcp_tenant_id", default=None)
mcp_user_subject: ContextVar[Optional[str]] = ContextVar(
    "mcp_user_subject", default=None
)


def set_mcp_caller(tenant: Optional[str], actor: Optional[str]) -> None:
    mcp_tenant_id.set((tenant or "").strip() or None)
    mcp_user_subject.set((actor or "").strip() or None)


def get_mcp_caller() -> tuple[str, Optional[str]]:
    """Return (tenant_id, user_subject) for the current MCP call.

    tenant_id falls back to "_global" so callers can pass it straight into
    `call_with_cascade` (which treats "_global" as no tenant context)."""
    return (mcp_tenant_id.get() or "_global", mcp_user_subject.get())
