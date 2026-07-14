# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""MCP tool reporting vault status. It never returns a secret's value."""

from __future__ import annotations

import json
import shutil
from typing import List

from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker

REGISTERED_TOOLS: List[str] = []


@mcp_server.tool()
@with_hooks("vault_status")
async def vault_status() -> str:
    """Vault snapshot — configured key list + last 5 audit events. No cleartext."""
    await tracker.bump("vault_status")
    from app.vault.audit import read_recent
    from app.vault.cache import is_loaded, known_keys
    from app.vault.runner import master_key_exists, sops_available

    payload = {
        "vault_enabled": sops_available() and master_key_exists(),
        "binary_sops": shutil.which("sops") is not None,
        "binary_age": shutil.which("age") is not None,
        "master_key_present": master_key_exists(),
        "keys": [{"name": k, "configured": is_loaded(k)} for k in known_keys()],
        "recent_audit": read_recent(limit=5),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


REGISTERED_TOOLS.extend(["vault_status"])
