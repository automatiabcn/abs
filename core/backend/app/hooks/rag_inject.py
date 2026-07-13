# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Offer what you already know before someone writes it again.

When a tool call looks like analysis or authoring, this searches the documents
the operator has actually indexed and passes back the closest few, so the model
answers from the organisation's own material rather than from scratch.

Two rules keep it from becoming noise. It says nothing when it has nothing —
an empty index, a failed lookup and a weak match are all silence, never a
placeholder. And it speaks at most once per five minutes for a given kind of
work, because context injected on every single call stops being read.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from .common import allow_once, load_rate, persist_rate, safe_hook

logger = logging.getLogger(__name__)

_RATE_FILE = "rag_inject_rate.json"
_WINDOW_SEC = 300  # once per five minutes, per kind of work

# Below this, a "match" is the index shrugging. Injecting it would be worse than
# injecting nothing: it reads as authoritative and it isn't.
_MIN_SCORE = 0.35
_TOP_K = 3
_LOOKUP_TIMEOUT_SEC = 5.0

# What to go looking for, given the work in front of us.
_QUESTION_FOR = {
    "bash_analysis": "How have we analysed data like this before?",
    "write_code": "Existing code and patterns for what is being written here.",
    "write_docs": "How our existing documentation is written and structured.",
}


def _run_blocking(coro: Any) -> Any:
    """Run the async RAG query from this synchronous hook.

    `asyncio.run` cannot be called from inside the event loop the API request
    lives in, so the coroutine gets a thread with a loop of its own.
    """
    import asyncio
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=_LOOKUP_TIMEOUT_SEC)


def _lookup(category: str) -> List[Dict[str, Any]]:
    """The closest few chunks, or nothing at all.

    Every failure here — no index, no embedding provider, a slow Qdrant — is a
    reason to stay quiet, not a reason to fail the tool call the operator was
    actually making.
    """
    question = _QUESTION_FOR.get(category)
    if not question:
        return []
    try:
        from app.rag.query import query

        hits = _run_blocking(query(question, top_k=_TOP_K)) or []
    except Exception as exc:  # noqa: BLE001 — a quiet hook beats a broken tool call
        logger.debug("rag_inject lookup skipped: %s", exc)
        return []

    return [
        h
        for h in hits
        if isinstance(h, dict)
        and not h.get("error")
        and h.get("snippet")
        and (h.get("score") or 0) >= _MIN_SCORE
    ]


def _category_for(tool: str, tool_input: dict) -> str:
    cmd = (tool_input or {}).get("command", "") or ""
    fp = (tool_input or {}).get("file_path", "") or ""

    if tool == "Bash" and any(
        k in cmd.lower() for k in ("analyze", "analyse", "compare", "filter", "aggregate")
    ):
        return "bash_analysis"
    if tool in ("Write", "Edit"):
        ext = os.path.splitext(fp)[1].lower()
        if ext in (".py", ".ts", ".tsx", ".js", ".go", ".rs"):
            return "write_code"
        if ext in (".md", ".mdx"):
            return "write_docs"
    return ""


@safe_hook("rag_inject")
def maybe_rag_inject(tool: str, tool_input: dict) -> str:
    if tool not in ("Bash", "Write", "Edit"):
        return ""

    category = _category_for(tool, tool_input)
    if not category:
        return ""

    key = f"{tool}:{category}"
    rate = load_rate(_RATE_FILE)
    if not allow_once(rate, key, _WINDOW_SEC):
        return ""
    persist_rate(_RATE_FILE, rate)

    hits = _lookup(category)
    if not hits:
        return ""

    lines = [
        f"- {h.get('file') or 'a document'}: {str(h['snippet']).strip()}" for h in hits
    ]
    body = "\n".join(lines)
    return f"FROM YOUR OWN DOCUMENTS:\n{body}"
