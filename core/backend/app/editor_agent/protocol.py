# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""How a model reply is read: as a tool call, or as the answer.

The protocol is ours, not a vendor's function-calling schema, for the same
reason the panel agent's is (app/agentic/loop.py): the cascade can move a
run from Groq to Cerebras to Gemini between one step and the next, and a
transcript in a shared shape survives that. It differs from the panel's in
one deliberate way: **the answer is plain prose, not JSON.** A final answer
wrapped in `{"action": "final", "answer": "…"}` cannot be streamed to the
developer as it is produced, and a mid-size model writing Markdown inside a
JSON string escapes it wrong about a third of the time. So:

    a tool call  →  exactly one JSON object   {"tool": "read_file", "args": {…}}
    the answer   →  Markdown, as you would write to the developer

Accepted in the tool position, because models reach for them out of habit:
`{"action":"tool","name":…,"args":…}`, `{"name":…,"arguments":…}`, a code
fence around any of them, and a sentence of prose before the object. What
is NOT accepted is guessing: a reply that starts like JSON and does not
parse is sent back for one repair turn rather than shown as an answer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

_FENCE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$", re.S)
_TOOL_KEYS = ("tool", "action", "name")


@dataclass
class Parsed:
    kind: str  # "tool" | "final" | "invalid"
    name: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    text: str = ""
    reason: str = ""


def _unfence(text: str) -> str:
    m = _FENCE.match(text)
    return m.group(1) if m else text


def _balanced_object(text: str, start: int) -> Optional[str]:
    """The JSON object that begins at `start`, found by brace matching that
    respects strings — a regex from `{` to the last `}` swallows the prose
    after a tool call and fails on any answer that mentions a dict."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _as_tool(obj: Any) -> Optional[Parsed]:
    if not isinstance(obj, dict):
        return None
    name = obj.get("tool")
    args = obj.get("args")
    if not isinstance(name, str):
        if obj.get("action") == "tool" and isinstance(obj.get("name"), str):
            name = obj["name"]
        elif isinstance(obj.get("name"), str) and "arguments" in obj:
            name = obj["name"]
            args = obj.get("arguments")
        elif obj.get("action") == "final":
            return Parsed("final", text=str(obj.get("answer") or obj.get("text") or ""))
        else:
            return None
    if args is None:
        args = obj.get("arguments", obj.get("parameters", {}))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    if not isinstance(args, dict):
        args = {}
    return Parsed("tool", name=name.strip(), args=args)


def looks_like_json_start(text: str) -> bool:
    """Whether the first bytes of a reply announce a tool call — decided on
    the stream's prefix so the developer is not shown half a JSON object
    while it arrives."""
    t = text.lstrip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t).lstrip()
    return t.startswith("{")


def parse_reply(text: str) -> Parsed:
    """Read one model reply."""
    raw = (text or "").strip()
    if not raw:
        return Parsed("invalid", reason="empty reply")
    body = _unfence(raw).strip()
    if body.startswith("{"):
        obj_text = _balanced_object(body, 0)
        if obj_text is None:
            return Parsed("invalid", reason="unterminated JSON object")
        try:
            obj = json.loads(obj_text)
        except ValueError:
            return Parsed("invalid", reason="JSON did not parse")
        tool = _as_tool(obj)
        if tool is not None:
            return tool
        return Parsed("invalid", reason="JSON object is not a tool call")
    # Prose with a tool object embedded ("I'll read it: {…}") — the object
    # is the intent; the prose around it was for nobody.
    for key in _TOOL_KEYS:
        i = body.find('{"%s"' % key)
        if i < 0:
            i = body.find("{ \"%s\"" % key)
        if i >= 0:
            obj_text = _balanced_object(body, i)
            if obj_text:
                try:
                    tool = _as_tool(json.loads(obj_text))
                except ValueError:
                    tool = None
                if tool is not None and tool.kind == "tool":
                    return tool
    return Parsed("final", text=raw)


REPAIR_NOTE = (
    "System: your last reply began like a tool call but was not a valid JSON "
    'object. Reply with exactly one object such as {"tool": "read_file", '
    '"args": {"path": "app/routes.py"}} — or, if you are answering the '
    "developer, write the answer as plain text with no JSON."
)
