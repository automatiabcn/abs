# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Notes MCP tools — the editor's Notion-like companion over /mcp.

Per-caller scoped (tenant → default). CRUD + lexical search.
"""

from __future__ import annotations

import json
from typing import List

from app.config import settings
from app.mcp.middleware import with_hooks
from app.mcp.server import mcp_server
from app.mcp.tracking import tracker
from app.notes import service as _notes

REGISTERED_TOOLS: List[str] = []


def _caller_key() -> str:
    try:
        from app.mcp.context import get_mcp_caller

        tenant, _user = get_mcp_caller()
        if tenant:
            return str(tenant)
    except Exception:
        pass
    return getattr(settings, "mcp_rag_tenant", None) or "default"


@mcp_server.tool()
@with_hooks("note_save")
async def note_save(
    title: str, body: str, note_id: str = "", project: str = "", tags: str = ""
) -> str:
    """Create or update a note. Pass note_id to update an existing one."""
    await tracker.bump("note_save")
    res = _notes.save(
        title,
        body,
        key=_caller_key(),
        note_id=note_id or None,
        project=project or None,
        tags=tags or None,
    )
    return json.dumps(res, ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("note_list")
async def note_list(limit: int = 50) -> str:
    """List notes, newest first (title + preview)."""
    await tracker.bump("note_list")
    return json.dumps(_notes.list_notes(key=_caller_key(), limit=limit), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("note_get")
async def note_get(note_id: str) -> str:
    """Fetch one note in full by id."""
    await tracker.bump("note_get")
    return json.dumps(_notes.get(note_id, key=_caller_key()), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("note_search")
async def note_search(query: str, top_k: int = 10) -> str:
    """Lexical search over notes."""
    await tracker.bump("note_search")
    return json.dumps(_notes.search(query, key=_caller_key(), top_k=top_k), ensure_ascii=False, indent=2)


@mcp_server.tool()
@with_hooks("note_delete")
async def note_delete(note_id: str) -> str:
    """Delete a note by id."""
    await tracker.bump("note_delete")
    return json.dumps({"deleted": _notes.delete(note_id, key=_caller_key())}, ensure_ascii=False)


REGISTERED_TOOLS.extend(
    ["note_save", "note_list", "note_get", "note_search", "note_delete"]
)
