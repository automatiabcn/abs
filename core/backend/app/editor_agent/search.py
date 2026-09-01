# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""semantic_search over the open project.

The index, when the project has been indexed, answers by meaning; otherwise
the same deterministic ranking Composer uses (term in file name, term in
body, graph neighbours) answers by words. Both return the same shape — a
few files with the lines that matched — so the model does not have to know
which one it got. What matters is that "where is the cart total computed?"
comes back with the files that mention totals, or with "nothing in the
project mentions this", and never with an invented route.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Sequence, Tuple

logger = logging.getLogger(__name__)

MAX_FILES = 6
SNIPPET_LINES = 3
MAX_MATCH_LINES = 12


def _terms(query: str) -> List[str]:
    from app.composer.runtime import _task_terms

    return [t for t in _task_terms(query) if len(t) >= 3]


def _snippets(body: str, terms: Sequence[str]) -> List[str]:
    out: List[str] = []
    for i, line in enumerate(body.splitlines()):
        low = line.lower()
        if any(t in low for t in terms):
            out.append(f"{i + 1}: {line.rstrip()[:160]}")
            if len(out) >= MAX_MATCH_LINES:
                break
    return out


async def semantic_search(
    *, root: str, query: str, tenant: str = "_global"
) -> Dict[str, Any]:
    """{ok, hits:[{path, lines:[...]}], source:'index'|'lexical', model_note}."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty", "model_note": "semantic_search: give a query."}

    from app.composer.runtime import relevant_files, workspace_files
    from app.codegraph.graph import tenant_key as _key_for

    listing = workspace_files(root)
    picked: List[Tuple[str, str]] = relevant_files(
        root, q, listing, graph_key=_key_for(tenant, root)
    )
    terms = _terms(q)
    hits: List[Dict[str, Any]] = []
    for rel, body in picked:
        lines = _snippets(body, terms)
        if lines:
            hits.append({"path": rel, "lines": lines})
    source = "lexical"
    # The vector index, when this project is in it, adds files the words
    # alone would miss. Best effort: no index is not an error.
    try:
        from app.rag.query import query as rag_query

        res = await rag_query(q, top_k=5, project_filter=None)  # type: ignore[call-arg]
        for item in res if isinstance(res, list) else []:
            p = str(item.get("file") or item.get("path") or "")
            if not p:
                continue
            rel = os.path.relpath(p, root) if os.path.isabs(p) else p
            if rel.startswith(".."):
                continue
            if any(h["path"] == rel for h in hits):
                continue
            snippet = str(item.get("snippet") or "")[:300]
            hits.append({"path": rel, "lines": [snippet] if snippet else []})
            source = "index+lexical"
    except Exception as exc:  # noqa: BLE001 — the index is optional
        logger.debug("semantic_search index skipped: %s", exc)

    hits = hits[:MAX_FILES]
    if not hits:
        note = (
            f"semantic_search: nothing in the project matches '{q}' "
            f"(terms: {', '.join(terms[:6]) or '-'}). If you expected something, try "
            "grep with a different word, or say it is not implemented."
        )
        return {"ok": True, "hits": [], "source": source, "model_note": note}
    lines = [f"semantic_search results for '{q}' ({source}):"]
    for h in hits:
        lines.append(f"--- {h['path']} ---")
        lines.extend(h["lines"] or ["(matched by name)"])
    return {"ok": True, "hits": hits, "source": source, "model_note": "\n".join(lines)}
