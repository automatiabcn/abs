# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Tools that read or change the whole server belong to the operator.

admin_overview (billing, security, compliance for the install), the judge
persona (one tuning applied to EVERY tenant's scores) and the workflow
durability readout (every tenant's runs) answered any token that knew the
tool's name (audit 2026-08-18). The operator is the setup admin — the same
identity app/providers/paid_access uses for the server's paid keys.
"""

from __future__ import annotations

from typing import Optional


def operator_refusal(tool_name: str) -> Optional[str]:
    """Why this caller may not run `tool_name` — or None when they may."""
    try:
        from app.mcp.context import get_mcp_caller

        _tenant, user = get_mcp_caller()
    except Exception:  # noqa: BLE001 — no MCP context: an in-process caller
        return None
    from app.providers.paid_access import is_operator

    if is_operator(user):
        return None
    return (
        f"{tool_name} reads or changes the whole server and is for the "
        f"operator (the setup admin); this token belongs to "
        f"{user or 'no signed-in user'}."
    )
