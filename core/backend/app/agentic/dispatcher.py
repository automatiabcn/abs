# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The tools the agent may reach for, and how one gets run.

The MCP surface carries ~121 tools. Handing all of them to a model would be the
easy move and the wrong one: most are operator plumbing (mint a licence, clear
the RAG store, run a paid provider), and a catalogue that large costs a small
model most of its context before it has read the question. What is curated here
is the set someone actually asks a business assistant for — what is the system
doing, what does it cost, what do our documents say — plus the handful of
consequential ones that exist to prove the approval gate works end to end.

Each entry declares its own JSON schema. The loop pastes these into the prompt,
so the schema is not documentation: it is the only description of the tool the
model ever sees, and a vague one produces vague arguments.
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.agentic.policy import Level, is_enabled

logger = logging.getLogger(__name__)

# A tool result longer than this is truncated before it re-enters the prompt.
# Two reasons, and the second is the important one: a 200 KB document blows the
# context window, and a large hostile payload gets more room to hide an injected
# instruction in. Truncation is announced in the text so the model knows it is
# looking at a fragment rather than silently reasoning from half a table.
MAX_RESULT_CHARS = 4000


@dataclass(frozen=True)
class Tool:
    name: str
    level: Level
    description: str
    parameters: Dict[str, Any]  # JSON Schema (object)
    fn: Callable[..., Awaitable[str]]
    required: List[str] = field(default_factory=list)


def _schema(**props: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "properties": props}


# --- L0: facts about this system. Read-only, always audited, never gated. ----
#
# Imports are lazy (inside the wrappers) because app.mcp.tools.* pulls in the
# FastMCP server and its provider adapters at import time; making the dispatcher
# depend on that at module scope would drag the whole MCP stack into every
# process that merely wants to *ask what tools exist*.


async def _system_status() -> str:
    from app.mcp.tools.status_tools import status_check

    return await status_check()


async def _quota_status() -> str:
    from app.mcp.tools.system_extras import quota_status

    return await quota_status()


async def _rag_query(question: str, top_k: int = 5) -> str:
    from app.mcp.tools.rag import rag_query

    return await rag_query(question, top_k=top_k)


async def _rag_status() -> str:
    from app.mcp.tools.rag import rag_status

    return await rag_status()


_TOOLS: Dict[str, Tool] = {}


def _register(tool: Tool) -> None:
    _TOOLS[tool.name] = tool


_register(
    Tool(
        name="system_status",
        level=Level.READ,
        description=(
            "Current health of this ABS server: providers standing, licence "
            "state, and business counters for the last 24 hours. Takes no "
            "arguments. Call this when asked how the system is doing."
        ),
        parameters=_schema(),
        fn=_system_status,
    )
)

_register(
    Tool(
        name="quota_status",
        level=Level.READ,
        description=(
            "Per-provider usage against its limit, as used/limit/percent. Call "
            "this for questions about cost, spend, remaining budget or whether "
            "a quota is close to running out."
        ),
        parameters=_schema(),
        fn=_quota_status,
    )
)

_register(
    Tool(
        name="rag_query",
        level=Level.READ,
        description=(
            "Search the company's indexed documents and return the passages "
            "that answer a question, each with its source. Use this for any "
            "question about the company's own material — contracts, meeting "
            "transcripts, internal notes — and quote only what comes back."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question, in the language it was asked.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "How many passages to return (default 5).",
                },
            },
            "required": ["question"],
        },
        fn=_rag_query,
        required=["question"],
    )
)

_register(
    Tool(
        name="rag_status",
        level=Level.READ,
        description=(
            "How much material is indexed and when it was last updated. Use "
            "this to answer 'do you have our documents?' before searching."
        ),
        parameters=_schema(),
        fn=_rag_status,
    )
)


# --- L1: files, inside the roots the operator opened up. ---------------------
#
# Registered unconditionally and filtered out of the catalogue by `is_enabled`
# when no root is configured — which is the default. An install that never sets
# agent_fs_roots never shows the model that these exist.


async def _fs_list(path: str = "") -> str:
    from app.agentic.fs_tools import fs_list

    return await fs_list(path)


async def _fs_read(path: str) -> str:
    from app.agentic.fs_tools import fs_read

    return await fs_read(path)


async def _fs_search(query: str, path: str = "") -> str:
    from app.agentic.fs_tools import fs_search

    return await fs_search(query, path)


_register(
    Tool(
        name="fs_list",
        level=Level.READ_FILE,
        description=(
            "List the files and folders at a path. Call it with no arguments "
            "first to see which folders you are allowed to read at all."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Folder to list. Omit to see the allowed folders.",
                }
            },
        },
        fn=_fs_list,
    )
)

_register(
    Tool(
        name="fs_read",
        level=Level.READ_FILE,
        description=(
            "Read one text file. Use fs_list or fs_search to find its path "
            "first — do not guess a path."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to the file."}
            },
            "required": ["path"],
        },
        fn=_fs_read,
        required=["path"],
    )
)

_register(
    Tool(
        name="fs_search",
        level=Level.READ_FILE,
        description=(
            "Find which files contain a piece of text. Returns paths and line "
            "numbers, not the text itself — open a result with fs_read to see it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to look for."},
                "path": {
                    "type": "string",
                    "description": "Folder to search in. Omit to search all allowed folders.",
                },
            },
            "required": ["query"],
        },
        fn=_fs_search,
        required=["query"],
    )
)


def catalogue() -> List[Tool]:
    """The tools this server currently offers the model.

    A tool whose level the operator has not enabled is left out entirely rather
    than listed-and-refused: a model cannot be argued into calling something it
    was never told about (see policy.py).
    """
    return [tool for tool in _TOOLS.values() if is_enabled(tool.level)]


def get(name: str) -> Optional[Tool]:
    return _TOOLS.get(name)


def describe_for_prompt() -> str:
    """The catalogue as the model sees it: name, purpose, argument schema."""
    lines: List[str] = []
    for tool in catalogue():
        lines.append(
            json.dumps(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)


class ToolCallError(Exception):
    """A tool call that could not be run as asked."""


def _validate(tool: Tool, args: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the arguments the tool declares, and insist on the required ones.

    Models invent parameters — a plausible-looking `project` or `format` that
    the signature never had. Passing those through raises TypeError deep inside
    the tool, which surfaces to the operator as a stack trace rather than as the
    model's mistake. Dropping them is both kinder and safer: the tool runs with
    exactly the inputs it declared, and nothing else reaches it.
    """
    if not isinstance(args, dict):
        raise ToolCallError("arguments must be an object")

    declared = set(tool.parameters.get("properties", {}))
    missing = [key for key in tool.required if key not in args]
    if missing:
        raise ToolCallError(f"missing required argument(s): {', '.join(missing)}")

    dropped = [key for key in args if key not in declared]
    if dropped:
        logger.info("agent tool %s: dropped unknown args %s", tool.name, dropped)

    return {key: value for key, value in args.items() if key in declared}


def _truncate(text: str) -> str:
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return (
        text[:MAX_RESULT_CHARS]
        + f"\n… [truncated, {len(text) - MAX_RESULT_CHARS} more characters]"
    )


async def run(name: str, args: Dict[str, Any]) -> str:
    """Run a curated tool. The policy gate is the caller's job, not this one's —
    the loop checks it before it ever gets here, and the approval path calls in
    only after a human has said yes."""
    tool = get(name)
    if tool is None:
        raise ToolCallError(f"unknown tool: {name}")

    clean = _validate(tool, args or {})
    result = tool.fn(**clean)
    if inspect.isawaitable(result):
        result = await result
    return _truncate(str(result))
