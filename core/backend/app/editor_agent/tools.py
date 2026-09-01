# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""The tools the editor's agent may call.

The set is deliberately the same ten every serious coding agent ships —
read, list, grep, search, diagnostics, diff, edit, create, run, plan — and
nothing operator-shaped. Each entry says where it runs: `editor` tools run
in the developer's editor against the open folder (the file never leaves
the machine); `server` tools run here because they need the index or the
patch engine.

`level` is the approval class the editor enforces: `read` runs freely,
`write` shows a diff card and waits for a click, `shell` waits for a click
unless the editor can prove the command is read-only. The model is told the
class so it can say "this will ask you first" rather than promise a result
it cannot yet see.

Two modes select from the catalogue. `ask` is read-only: the model may look
anywhere but changes nothing. `agent` has all of it.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

Tool = Dict[str, Any]


def _t(
    name: str,
    where: str,
    level: str,
    description: str,
    properties: Dict[str, Any],
    required: List[str],
) -> Tool:
    return {
        "name": name,
        "where": where,
        "level": level,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


TOOLS: List[Tool] = [
    _t(
        "read_file",
        "editor",
        "read",
        "Read a file from the open project. Returns numbered lines. For a file "
        "longer than ~300 lines, pass start_line/end_line (1-based, inclusive) "
        "and read the part you need.",
        {
            "path": {"type": "string", "description": "workspace-relative path, e.g. app/routes.py"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        },
        ["path"],
    ),
    _t(
        "list_dir",
        "editor",
        "read",
        "List the files and folders under a path of the open project ('' for the root).",
        {"path": {"type": "string", "description": "workspace-relative folder, '' for the root"}},
        [],
    ),
    _t(
        "grep",
        "editor",
        "read",
        "Search the project's text for a regular expression. Returns path:line: text "
        "for up to max_results matches. Use it to find where something is defined "
        "or used before answering about it.",
        {
            "pattern": {"type": "string", "description": "regular expression (case-insensitive)"},
            "glob": {"type": "string", "description": "optional file filter, e.g. **/*.py"},
            "max_results": {"type": "integer", "description": "default 40"},
        },
        ["pattern"],
    ),
    _t(
        "semantic_search",
        "server",
        "read",
        "Find the files and snippets most related to a question, by meaning rather "
        "than by exact text. Good first step for 'where is X handled?'.",
        {"query": {"type": "string"}},
        ["query"],
    ),
    _t(
        "get_diagnostics",
        "editor",
        "read",
        "The editor's current errors and warnings (from linters and language servers), "
        "for one file or the whole project. Call it after an edit to see what broke.",
        {"path": {"type": "string", "description": "optional workspace-relative path"}},
        [],
    ),
    _t(
        "git_diff",
        "editor",
        "read",
        "The uncommitted changes in the project (new files included) — what the "
        "developer changed since the last commit. Call it when they say they "
        "changed something and want it checked.",
        {"path": {"type": "string", "description": "optional: limit to one path"}},
        [],
    ),
    _t(
        "propose_edit",
        "server",
        "write",
        "Change one file. Give the exact text to find (`search`, copied verbatim "
        "from a read_file result, including indentation, at least 3 lines so it is "
        "unique) and the text to put in its place (`replace`). The edit is checked, "
        "graded, shown to the developer as a diff, and applied only when they "
        "approve; the result tells you whether it was applied. To rewrite a whole "
        "small file, pass `new_content` instead of search/replace.",
        {
            "path": {"type": "string"},
            "search": {"type": "string"},
            "replace": {"type": "string"},
            "new_content": {"type": "string"},
            "rationale": {"type": "string", "description": "one sentence: why this change"},
        },
        ["path"],
    ),
    _t(
        "create_file",
        "editor",
        "write",
        "Create a new file with the given content. Fails if the file exists (use "
        "propose_edit for that). Shown to the developer and applied when they approve.",
        {"path": {"type": "string"}, "content": {"type": "string"}},
        ["path", "content"],
    ),
    _t(
        "run_command",
        "editor",
        "shell",
        "Run a shell command in the project folder and read its output (stdout+stderr, "
        "exit code). Read-only commands (ls, git status, cat, grep) run at once; "
        "anything else waits for the developer's approval.",
        {
            "command": {"type": "string"},
            "timeout_s": {"type": "integer", "description": "default 60"},
        },
        ["command"],
    ),
    _t(
        "run_tests",
        "editor",
        "shell",
        "Run the project's tests (pytest, npm test, go test, cargo test — detected) "
        "or the command you give, and read the result. Use it to verify a change.",
        {
            "command": {"type": "string", "description": "optional explicit test command"},
            "path": {"type": "string", "description": "optional: only this test file/dir"},
        },
        [],
    ),
    _t(
        "update_plan",
        "editor",
        "read",
        "Keep the task list for this conversation. Write the whole list each time: "
        "id, text, status (todo | doing | done). The developer sees it; the next "
        "turn starts from it. Use it for any task with more than one step, and "
        "update a step to done when it is.",
        {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                        "status": {"type": "string", "enum": ["todo", "doing", "done"]},
                    },
                    "required": ["id", "text", "status"],
                },
            }
        },
        ["todos"],
    ),
    _t(
        "ask_user",
        "editor",
        "read",
        "Ask the developer one question when you truly cannot proceed without their "
        "decision (which of two designs, a value only they know). Never use it to "
        "ask for a file or code that is in the project — read it yourself.",
        {
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
        },
        ["question"],
    ),
]

_BY_NAME: Dict[str, Tool] = {t["name"]: t for t in TOOLS}

MODES = ("ask", "agent")


def catalogue(mode: str) -> List[Tool]:
    """The tools one mode offers. Unknown modes are `ask` — the safe end."""
    if mode == "agent":
        return list(TOOLS)
    return [t for t in TOOLS if t["level"] == "read"]


def get(name: str) -> Tool | None:
    return _BY_NAME.get(name)


def allowed(name: str, mode: str) -> bool:
    return any(t["name"] == name for t in catalogue(mode))


def _sig(t: Tool) -> str:
    props = t["parameters"].get("properties", {})
    req = set(t["parameters"].get("required", []))
    parts = []
    for name, spec in props.items():
        typ = spec.get("type", "string")
        if typ == "array":
            typ = "array of " + str((spec.get("items") or {}).get("type", "object"))
        parts.append(f"{name}: {typ}" + ("" if name in req else "?"))
    return f"{t['name']}({', '.join(parts)})"


def describe_for_prompt(mode: str) -> str:
    """The catalogue as the model sees it: one line per tool, signature
    then purpose. Compact on purpose — every step re-sends it, and on a
    free-tier provider the prompt's size is the loop's speed."""
    lines = []
    for t in catalogue(mode):
        gate = " [asks the developer first]" if t["level"] != "read" else ""
        lines.append(f"- {_sig(t)}{gate}: {t['description']}")
    return "\n".join(lines)


def describe_json(mode: str) -> str:
    """The catalogue as JSON Schema, for native function-calling providers."""
    return json.dumps(
        [
            {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            for t in catalogue(mode)
        ],
        ensure_ascii=False,
    )


def validate_args(tool: Tool, args: Any) -> Dict[str, Any]:
    """Only declared arguments reach a tool, and the required ones must be
    there. Models invent parameters; passing them on turns the model's slip
    into a tool failure that looks like ours."""
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")
    props = tool["parameters"].get("properties", {})
    missing = [k for k in tool["parameters"].get("required", []) if k not in args]
    if missing:
        raise ValueError(f"missing required argument(s): {', '.join(missing)}")
    return {k: v for k, v in args.items() if k in props}
